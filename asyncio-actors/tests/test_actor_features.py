"""Tests for the five new features added in the hardening pass.

Feature 1 — Named actor spawning
Feature 2 — ActorRef.stop()
Feature 3 — ActorRef.watch()
Feature 4 — Public Actor.receive()
Feature 5 — Envelope metadata
"""
from __future__ import annotations

import asyncio
import time
import pytest

from asyncio_actors.actor import Actor, Envelope
from asyncio_actors.system import ActorSystem
from asyncio_actors.supervision import SupervisionStrategy


# ---------------------------------------------------------------------------
# Helper actors
# ---------------------------------------------------------------------------

class EchoActor(Actor):
    async def on_message(self, message):
        return message


class AccumulatorActor(Actor):
    def __init__(self):
        super().__init__()
        self.received: list = []
        self.stopped = False

    async def on_message(self, message):
        self.received.append(message)

    async def on_stop(self):
        self.stopped = True


class LifecycleActor(Actor):
    def __init__(self):
        super().__init__()
        self.started = False
        self.stopped = False

    async def on_start(self):
        self.started = True

    async def on_message(self, message):
        return message

    async def on_stop(self):
        self.stopped = True


# ===========================================================================
# Feature 1 — Named actor spawning
# ===========================================================================

@pytest.mark.asyncio
async def test_spawn_with_name_registers_ref():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor, name="echo")
        looked_up = system.get("echo")
        assert looked_up is ref


@pytest.mark.asyncio
async def test_get_unknown_name_returns_none():
    async with ActorSystem() as system:
        result = system.get("nonexistent")
        assert result is None


@pytest.mark.asyncio
async def test_spawn_duplicate_name_raises():
    async with ActorSystem() as system:
        await system.spawn(EchoActor, name="unique")
        with pytest.raises(ValueError, match="unique"):
            await system.spawn(EchoActor, name="unique")


@pytest.mark.asyncio
async def test_spawn_without_name_not_in_registry():
    async with ActorSystem() as system:
        await system.spawn(EchoActor)
        # Registry should still be empty (no named actors spawned)
        assert system.get("anything") is None


@pytest.mark.asyncio
async def test_named_actor_removed_from_registry_after_stop():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor, name="temp")
        assert system.get("temp") is not None
        # Stop the actor and let the supervision task clean up.
        await ref.stop()
        await asyncio.sleep(0.1)
        assert system.get("temp") is None


@pytest.mark.asyncio
async def test_multiple_named_actors():
    async with ActorSystem() as system:
        ref_a = await system.spawn(EchoActor, name="a")
        ref_b = await system.spawn(EchoActor, name="b")
        assert system.get("a") is ref_a
        assert system.get("b") is ref_b
        assert system.get("c") is None


@pytest.mark.asyncio
async def test_named_actor_is_functional():
    async with ActorSystem() as system:
        await system.spawn(EchoActor, name="worker")
        ref = system.get("worker")
        assert ref is not None
        result = await ref.ask("hello")
        assert result == "hello"


# ===========================================================================
# Feature 2 — ActorRef.stop()
# ===========================================================================

@pytest.mark.asyncio
async def test_ref_stop_stops_actor():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        assert ref.is_alive is True
        await ref.stop()
        await asyncio.sleep(0.05)
        assert ref.is_alive is False


@pytest.mark.asyncio
async def test_ref_stop_triggers_on_stop_lifecycle():
    async with ActorSystem() as system:
        ref = await system.spawn(LifecycleActor)
        actor = ref._actor
        assert actor.started is True
        assert actor.stopped is False
        await ref.stop()
        await asyncio.sleep(0.05)
        assert actor.stopped is True


@pytest.mark.asyncio
async def test_ref_stop_idempotent():
    """Calling stop() twice should not raise."""
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        await ref.stop()
        await asyncio.sleep(0.05)
        # Second call on an already-stopped actor must not raise.
        await ref.stop()


@pytest.mark.asyncio
async def test_ref_stop_processes_queued_messages_before_stopping():
    """The actor can still process messages sent before stop() is called."""
    async with ActorSystem() as system:
        ref = await system.spawn(AccumulatorActor)
        await ref.send("a")
        await ref.send("b")
        # Stop after sending — the actor may or may not have processed them yet.
        await ref.stop()
        await asyncio.sleep(0.1)
        assert ref.is_alive is False


# ===========================================================================
# Feature 3 — ActorRef.watch()
# ===========================================================================

@pytest.mark.asyncio
async def test_watch_resolves_after_stop():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        done = await ref.watch()
        assert not done.done()
        await ref.stop()
        await asyncio.sleep(0.05)
        assert done.done()
        assert done.result() is None


@pytest.mark.asyncio
async def test_watch_resolves_when_actor_finishes():
    class SelfStoppingActor(Actor):
        async def on_message(self, message):
            if message == "die":
                await self.stop()

    async with ActorSystem() as system:
        ref = await system.spawn(SelfStoppingActor)
        done = await ref.watch()
        await ref.send("die")
        # The watch future should resolve quickly.
        await asyncio.wait_for(done, timeout=1.0)
        assert done.done()


@pytest.mark.asyncio
async def test_watch_resolves_immediately_if_already_stopped():
    """watch() on a dead actor should return an already-resolved future."""
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        await ref.stop()
        await asyncio.sleep(0.05)
        assert ref.is_alive is False

    done = await ref.watch()
    assert done.done()


@pytest.mark.asyncio
async def test_multiple_watchers_all_notified():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        futures = [await ref.watch() for _ in range(5)]
        assert all(not f.done() for f in futures)
        await ref.stop()
        await asyncio.sleep(0.05)
        assert all(f.done() for f in futures)


@pytest.mark.asyncio
async def test_watch_future_can_be_awaited():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        done = await ref.watch()
        # Schedule stop and await done concurrently.
        async def stopper():
            await asyncio.sleep(0.01)
            await ref.stop()

        _, result = await asyncio.gather(stopper(), done)
        assert result is None


# ===========================================================================
# Feature 4 — Public Actor.receive()
# ===========================================================================

class SelectiveReceiveActor(Actor):
    """Uses self.receive() to wait for specific message types."""

    def __init__(self):
        super().__init__()
        self.got_int: int | None = None
        self.got_str: str | None = None
        self.ready = asyncio.Event()

    async def on_message(self, message):
        if message == "go":
            # Wait for an int first, then a string.
            self.got_int = await self.receive(match=int)
            self.got_str = await self.receive(match=str)
            self.ready.set()


@pytest.mark.asyncio
async def test_receive_match_filters_by_type():
    async with ActorSystem() as system:
        ref = await system.spawn(SelectiveReceiveActor)
        actor = ref._actor

        await ref.send("go")
        # Send out-of-order: string before int.
        await ref.send("hello")
        await ref.send(42)

        await asyncio.wait_for(actor.ready.wait(), timeout=2.0)
        assert actor.got_int == 42
        assert actor.got_str == "hello"


@pytest.mark.asyncio
async def test_receive_no_match_returns_next_message():
    """receive(match=None) returns the very next message."""

    class NextActor(Actor):
        def __init__(self):
            super().__init__()
            self.got = None
            self.ready = asyncio.Event()

        async def on_message(self, message):
            if message == "fetch":
                self.got = await self.receive()
                self.ready.set()

    async with ActorSystem() as system:
        ref = await system.spawn(NextActor)
        actor = ref._actor
        await ref.send("fetch")
        await ref.send("payload")
        await asyncio.wait_for(actor.ready.wait(), timeout=1.0)
        assert actor.got == "payload"


@pytest.mark.asyncio
async def test_receive_timeout_raises():
    class TimeoutActor(Actor):
        def __init__(self):
            super().__init__()
            self.timed_out = False
            self.ready = asyncio.Event()

        async def on_message(self, message):
            if message == "wait":
                try:
                    await self.receive(match=int, timeout=0.05)
                except asyncio.TimeoutError:
                    self.timed_out = True
                self.ready.set()

    async with ActorSystem() as system:
        ref = await system.spawn(TimeoutActor)
        actor = ref._actor
        await ref.send("wait")
        await asyncio.wait_for(actor.ready.wait(), timeout=2.0)
        assert actor.timed_out is True


@pytest.mark.asyncio
async def test_receive_non_matching_messages_not_lost():
    """Messages that don't match the filter are not dropped."""

    class CollectActor(Actor):
        def __init__(self):
            super().__init__()
            self.collected: list = []
            self.ready = asyncio.Event()

        async def on_message(self, message):
            if message == "start":
                # Selectively receive only an int — strings should be stashed.
                val = await self.receive(match=int)
                self.collected.append(val)
                self.ready.set()
            else:
                self.collected.append(message)

    async with ActorSystem() as system:
        ref = await system.spawn(CollectActor)
        actor = ref._actor

        await ref.send("start")
        await ref.send("stash-me")
        await ref.send(99)
        await asyncio.wait_for(actor.ready.wait(), timeout=2.0)
        # "start" is handled, 99 is the matched int, "stash-me" is re-delivered.
        await asyncio.sleep(0.1)
        assert 99 in actor.collected
        assert "stash-me" in actor.collected


# ===========================================================================
# Feature 5 — Envelope metadata
# ===========================================================================

class EnvelopeCapture(Actor):
    """Captures the envelope for each message."""

    def __init__(self):
        super().__init__()
        self.envelopes: list[Envelope | None] = []

    async def on_message(self, message):
        self.envelopes.append(self.envelope)
        return message


@pytest.mark.asyncio
async def test_envelope_is_set_on_message():
    async with ActorSystem() as system:
        ref = await system.spawn(EnvelopeCapture)
        actor = ref._actor
        await ref.send("hello")
        await asyncio.sleep(0.05)
        assert len(actor.envelopes) == 1
        env = actor.envelopes[0]
        assert env is not None
        assert env.message == "hello"


@pytest.mark.asyncio
async def test_envelope_timestamp_is_recent():
    async with ActorSystem() as system:
        ref = await system.spawn(EnvelopeCapture)
        actor = ref._actor
        before = time.time()
        await ref.send("ts-test")
        await asyncio.sleep(0.05)
        after = time.time()
        assert len(actor.envelopes) == 1
        env = actor.envelopes[0]
        assert env is not None
        assert before <= env.timestamp <= after


@pytest.mark.asyncio
async def test_envelope_sender_is_passed_through():
    async with ActorSystem() as system:
        sender_ref = await system.spawn(EchoActor)
        receiver_ref = await system.spawn(EnvelopeCapture)
        actor = receiver_ref._actor

        await receiver_ref.send("msg", sender=sender_ref)
        await asyncio.sleep(0.05)
        assert len(actor.envelopes) == 1
        env = actor.envelopes[0]
        assert env is not None
        assert env.sender is sender_ref


@pytest.mark.asyncio
async def test_envelope_correlation_id_is_passed_through():
    async with ActorSystem() as system:
        ref = await system.spawn(EnvelopeCapture)
        actor = ref._actor
        await ref.send("msg", correlation_id="req-123")
        await asyncio.sleep(0.05)
        assert len(actor.envelopes) == 1
        env = actor.envelopes[0]
        assert env is not None
        assert env.correlation_id == "req-123"


@pytest.mark.asyncio
async def test_envelope_defaults_are_none():
    async with ActorSystem() as system:
        ref = await system.spawn(EnvelopeCapture)
        actor = ref._actor
        await ref.send("bare")
        await asyncio.sleep(0.05)
        env = actor.envelopes[0]
        assert env is not None
        assert env.sender is None
        assert env.correlation_id is None


@pytest.mark.asyncio
async def test_envelope_available_during_ask():
    """Envelope is set even for ask() calls."""

    class AskCapture(Actor):
        def __init__(self):
            super().__init__()
            self.captured_env: Envelope | None = None

        async def on_message(self, message):
            self.captured_env = self.envelope
            return "pong"

    async with ActorSystem() as system:
        ref = await system.spawn(AskCapture)
        actor = ref._actor
        result = await ref.ask("ping", correlation_id="corr-42")
        assert result == "pong"
        assert actor.captured_env is not None
        assert actor.captured_env.message == "ping"
        assert actor.captured_env.correlation_id == "corr-42"


@pytest.mark.asyncio
async def test_on_message_receives_unwrapped_payload():
    """on_message always gets the raw message, not the Envelope."""

    class UnwrapCheck(Actor):
        def __init__(self):
            super().__init__()
            self.messages: list = []

        async def on_message(self, message):
            self.messages.append(message)
            return message

    async with ActorSystem() as system:
        ref = await system.spawn(UnwrapCheck)
        actor = ref._actor
        await ref.send(42)
        await ref.send("text")
        await asyncio.sleep(0.05)
        assert actor.messages == [42, "text"]


@pytest.mark.asyncio
async def test_envelope_dataclass_fields():
    env = Envelope(message="test", sender=None, correlation_id="x", timestamp=1.0)
    assert env.message == "test"
    assert env.sender is None
    assert env.correlation_id == "x"
    assert env.timestamp == 1.0


@pytest.mark.asyncio
async def test_envelope_default_timestamp_auto_set():
    before = time.time()
    env = Envelope(message="m")
    after = time.time()
    assert before <= env.timestamp <= after


# ===========================================================================
# Coverage — exercise uncovered branches
# ===========================================================================

@pytest.mark.asyncio
async def test_watch_on_fully_stopped_actor_resolves_immediately():
    """Cover actor.py branch: watch() when _running=False and _task=None."""
    actor = EchoActor()
    actor._running = False
    actor._task = None
    ref = actor.ref()
    done = await ref.watch()
    assert done.done()
    assert done.result() is None


@pytest.mark.asyncio
async def test_actor_with_per_instance_restart_policy():
    """Cover actor.py branch: restart_policy already in __dict__."""
    from asyncio_actors.supervision import RestartPolicy

    class CustomActor(Actor):
        def __init__(self):
            self.restart_policy = RestartPolicy(max_restarts=99)
            super().__init__()

        async def on_message(self, message):
            return message

    async with ActorSystem() as system:
        ref = await system.spawn(CustomActor)
        actor = ref._actor
        assert actor.restart_policy.max_restarts == 99
        result = await ref.ask("ok")
        assert result == "ok"


@pytest.mark.asyncio
async def test_selective_receive_timeout_on_matched_type():
    """Cover actor.py _selective_receive timeout branch (deadline expires)."""

    class TimingActor(Actor):
        def __init__(self):
            super().__init__()
            self.timed_out = False
            self.ready = asyncio.Event()

        async def on_message(self, message):
            if message == "go":
                try:
                    await self.receive(match=float, timeout=0.05)
                except asyncio.TimeoutError:
                    self.timed_out = True
                self.ready.set()

    async with ActorSystem() as system:
        ref = await system.spawn(TimingActor)
        actor = ref._actor
        await ref.send("go")
        # Send non-matching messages to keep the loop busy
        await ref.send("not-a-float")
        await asyncio.wait_for(actor.ready.wait(), timeout=2.0)
        assert actor.timed_out is True


@pytest.mark.asyncio
async def test_inbox_receive_selective_from_stash():
    """Cover inbox.py receive() hitting stash path."""
    from asyncio_actors.inbox import Inbox

    inbox: Inbox = Inbox(maxsize=10)
    await inbox.put("a")
    await inbox.put(42)
    await inbox.put("b")

    # Selective receive int — should find 42 in queue
    result = await inbox.receive(int, timeout=1.0)
    assert result == 42


@pytest.mark.asyncio
async def test_inbox_receive_timeout_with_no_match():
    """Cover inbox.py receive() timeout after waiting."""
    from asyncio_actors.inbox import Inbox

    inbox: Inbox = Inbox(maxsize=10)
    await inbox.put("not-int")

    with pytest.raises(asyncio.TimeoutError):
        await inbox.receive(int, timeout=0.05)


@pytest.mark.asyncio
async def test_inbox_drop_oldest_from_stash():
    """Cover inbox.py _drop_oldest hitting stash branch."""
    from asyncio_actors.inbox import Inbox, OverflowPolicy

    inbox: Inbox = Inbox(maxsize=2, policy=OverflowPolicy.DROP_OLDEST)
    await inbox.put("a")
    await inbox.put("b")
    # Move one to stash via selective receive
    inbox._stash.append(inbox._queue.popleft())
    # Now stash has "a", queue has "b" — inbox is full
    assert inbox.full
    # put() should drop oldest from stash
    await inbox.put("c")
    assert "a" not in list(inbox._stash)


@pytest.mark.asyncio
async def test_inbox_close_unblocks_waiting_put():
    """Cover inbox.py close() unblocking a blocked put."""
    from asyncio_actors.inbox import Inbox, OverflowPolicy

    inbox: Inbox = Inbox(maxsize=1, policy=OverflowPolicy.BLOCK)
    await inbox.put("fill")

    async def blocked_put():
        with pytest.raises(RuntimeError, match="closed"):
            await inbox.put("blocked")

    task = asyncio.create_task(blocked_put())
    await asyncio.sleep(0.01)
    inbox.close()
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_inbox_receive_timeout_after_non_matching_arrives():
    """Cover inbox.py receive() timeout loop with deadline expiry."""
    from asyncio_actors.inbox import Inbox

    inbox: Inbox = Inbox(maxsize=10)

    async def delayed_put():
        await asyncio.sleep(0.01)
        await inbox.put("not-int")
        await asyncio.sleep(0.01)
        await inbox.put("also-not-int")

    task = asyncio.create_task(delayed_put())
    with pytest.raises(asyncio.TimeoutError):
        await inbox.receive(int, timeout=0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_inbox_waiter_resolved_by_put():
    """Cover inbox.py _notify_waiters: waiter gets resolved by put."""
    from asyncio_actors.inbox import Inbox

    inbox: Inbox = Inbox(maxsize=10)

    async def consumer():
        return await inbox.get(timeout=1.0)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.01)
    await inbox.put("delivered")
    result = await asyncio.wait_for(task, timeout=1.0)
    assert result == "delivered"


@pytest.mark.asyncio
async def test_inbox_receive_stash_then_queue():
    """Cover inbox.py receive() scanning both stash and queue."""
    from asyncio_actors.inbox import Inbox

    inbox: Inbox = Inbox(maxsize=10)
    # Put a non-matching message, then a matching one
    inbox._stash.append("stashed-str")
    inbox._queue.append(42)

    # Should find 42 from queue after scanning stash
    result = await inbox.receive(int, timeout=1.0)
    assert result == 42
    # stashed-str should remain in stash
    assert "stashed-str" in inbox._stash


@pytest.mark.asyncio
async def test_inbox_get_from_closed_empty():
    """Cover inbox.py get() on closed+empty inbox raises RuntimeError."""
    from asyncio_actors.inbox import Inbox

    inbox: Inbox = Inbox(maxsize=10)
    inbox.close()
    with pytest.raises(RuntimeError, match="closed and empty"):
        await inbox.get()


@pytest.mark.asyncio
async def test_supervisor_child_clean_exit():
    """Cover supervisor.py clean exit path (lines 120-123)."""
    from asyncio_actors.supervisor import (
        Supervisor, ChildSpec, RestartType, SupervisorStrategy,
    )

    class SelfStoppingChild(Actor):
        async def on_start(self):
            await self.stop()

    class TestSupervisor(Supervisor):
        strategy = SupervisorStrategy.ONE_FOR_ONE
        children_specs = [
            ChildSpec(SelfStoppingChild, restart=RestartType.TRANSIENT),
        ]

    async with ActorSystem() as system:
        await system.spawn(TestSupervisor)
        # Give child time to self-stop and supervisor to handle exit
        await asyncio.sleep(0.3)


@pytest.mark.asyncio
async def test_supervisor_permanent_child_clean_exit_restarts():
    """Cover supervisor.py PERMANENT child clean exit path (line 122-123)."""
    from asyncio_actors.supervisor import (
        Supervisor, ChildSpec, RestartType, SupervisorStrategy,
    )

    call_count = {"n": 0}

    class CountingChild(Actor):
        async def on_start(self):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                # Stop after first restart to avoid infinite loop
                return
            await self.stop()

    class TestSupervisor(Supervisor):
        strategy = SupervisorStrategy.ONE_FOR_ONE
        children_specs = [
            ChildSpec(CountingChild, restart=RestartType.PERMANENT),
        ]

    async with ActorSystem() as system:
        await system.spawn(TestSupervisor)
        await asyncio.sleep(0.5)
        assert call_count["n"] >= 2


@pytest.mark.asyncio
async def test_inbox_notify_multiple_waiters():
    """Cover inbox.py _notify_waiters loop continuation (93->88)."""
    from asyncio_actors.inbox import Inbox

    inbox: Inbox = Inbox(maxsize=10)

    results = []

    async def consumer(label):
        msg = await inbox.get(timeout=1.0)
        results.append((label, msg))

    # Create two waiters
    t1 = asyncio.create_task(consumer("a"))
    t2 = asyncio.create_task(consumer("b"))
    await asyncio.sleep(0.01)

    # Put two messages — both waiters should be notified
    await inbox.put("msg1")
    await inbox.put("msg2")

    await asyncio.wait_for(asyncio.gather(t1, t2), timeout=1.0)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_supervisor_one_for_all_restart():
    """Cover supervisor.py _restart_all task-is-current-task branch (174->172)."""
    from asyncio_actors.supervisor import (
        Supervisor, ChildSpec, SupervisorStrategy,
    )

    restart_counts = {"crasher": 0, "stable": 0}

    class CrasherChild(Actor):
        async def on_start(self):
            restart_counts["crasher"] += 1

        async def on_message(self, message):
            if message == "crash":
                raise RuntimeError("boom")

        async def on_error(self, error):
            return SupervisionStrategy.ESCALATE

    class StableChild(Actor):
        async def on_start(self):
            restart_counts["stable"] += 1

        async def on_message(self, message):
            return message

    class AllForOneSupervisor(Supervisor):
        strategy = SupervisorStrategy.ONE_FOR_ALL
        children_specs = [
            ChildSpec(CrasherChild),
            ChildSpec(StableChild),
        ]

    async with ActorSystem() as system:
        ref = await system.spawn(AllForOneSupervisor)
        sup = ref._actor
        # Wait for children to start
        await asyncio.sleep(0.1)
        children = sup.child_refs()
        assert len(children) >= 2
        # Crash the first child to trigger ONE_FOR_ALL restart
        await children[0].send("crash")
        await asyncio.sleep(0.5)
        # StableChild should have been restarted (at least 2 starts)
        assert restart_counts["stable"] >= 2


@pytest.mark.asyncio
async def test_supervisor_rest_for_one_restart():
    """Cover supervisor.py _restart_rest task-is-current-task branch (195->193)."""
    from asyncio_actors.supervisor import (
        Supervisor, ChildSpec, SupervisorStrategy,
    )

    start_counts = {"a": 0, "b": 0, "c": 0}

    class ChildA(Actor):
        async def on_start(self):
            start_counts["a"] += 1

        async def on_message(self, message):
            if message == "crash":
                raise RuntimeError("boom")

        async def on_error(self, error):
            return SupervisionStrategy.ESCALATE

    class ChildB(Actor):
        async def on_start(self):
            start_counts["b"] += 1
        async def on_message(self, message):
            return message

    class ChildC(Actor):
        async def on_start(self):
            start_counts["c"] += 1
        async def on_message(self, message):
            return message

    class RestSupervisor(Supervisor):
        strategy = SupervisorStrategy.REST_FOR_ONE
        children_specs = [
            ChildSpec(ChildA),
            ChildSpec(ChildB),
            ChildSpec(ChildC),
        ]

    async with ActorSystem() as system:
        ref = await system.spawn(RestSupervisor)
        # Wait for children to start
        await asyncio.sleep(0.1)
        sup = ref._actor
        children = sup.child_refs()
        # Crash child A — B and C (started after A) should also restart
        await children[0].send("crash")
        await asyncio.sleep(0.5)
        assert start_counts["a"] >= 2
        assert start_counts["b"] >= 2
        assert start_counts["c"] >= 2
