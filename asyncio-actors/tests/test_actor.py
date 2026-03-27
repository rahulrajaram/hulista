"""Tests for Actor, ActorRef, and ActorSystem."""
from __future__ import annotations

import asyncio
import pytest

from asyncio_actors.actor import Actor, ActorRef
from asyncio_actors.system import ActorSystem
from asyncio_actors.supervision import SupervisionStrategy, RestartPolicy
from asyncio_actors.inbox import OverflowPolicy


# ---------------------------------------------------------------------------
# Helper actors
# ---------------------------------------------------------------------------

class EchoActor(Actor):
    """Returns the message unchanged."""

    async def on_message(self, message):
        return message


class AccumulatorActor(Actor):
    """Appends every message to a list."""

    def __init__(self):
        super().__init__()
        self.received: list = []
        self.started = False
        self.stopped = False

    async def on_start(self):
        self.started = True

    async def on_message(self, message):
        self.received.append(message)

    async def on_stop(self):
        self.stopped = True


class StopOnErrorActor(Actor):
    """Returns STOP strategy on any error."""

    async def on_message(self, message):
        if message == "boom":
            raise ValueError("boom!")
        return message

    async def on_error(self, error):
        return SupervisionStrategy.STOP


class EscalateOnErrorActor(Actor):
    """Returns ESCALATE strategy — causes the run loop to re-raise."""

    async def on_message(self, message):
        raise RuntimeError("escalate!")

    async def on_error(self, error):
        return SupervisionStrategy.ESCALATE


class CountingActor(Actor):
    """Counts how many times on_start has been called (tracks restarts)."""

    restart_policy = RestartPolicy(max_restarts=2, restart_window_seconds=60.0)

    def __init__(self):
        super().__init__()
        self.start_count = 0
        self.stop_count = 0

    async def on_start(self):
        self.start_count += 1

    async def on_stop(self):
        self.stop_count += 1

    async def on_message(self, message):
        if message == "crash":
            raise RuntimeError("crash!")
        return message

    async def on_error(self, error):
        # ESCALATE so the system sees the crash and restarts.
        return SupervisionStrategy.ESCALATE


class ReplyActor(Actor):
    """Uses explicit self.reply() inside on_message."""

    async def on_message(self, message):
        await self.reply(f"got:{message}")
        # Return None; the reply was sent manually.


# ---------------------------------------------------------------------------
# Basic spawning and send
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spawn_and_send():
    async with ActorSystem() as system:
        ref = await system.spawn(AccumulatorActor)
        await ref.send("hello")
        await ref.send("world")
        # Give the actor time to process.
        await asyncio.sleep(0.05)
        # Retrieve the underlying actor to inspect state.
        actor = ref._actor
        assert actor.received == ["hello", "world"]


@pytest.mark.asyncio
async def test_lifecycle_on_start_on_stop():
    actor = AccumulatorActor()
    async with ActorSystem() as system:
        ref = await system.spawn(AccumulatorActor)
        inner_actor = ref._actor
        assert inner_actor.started is True
    # After the context exits the system stops all actors.
    assert inner_actor.stopped is True


# ---------------------------------------------------------------------------
# ask / reply
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_echo():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        result = await ref.ask("ping")
        assert result == "ping"


@pytest.mark.asyncio
async def test_ask_explicit_reply():
    async with ActorSystem() as system:
        ref = await system.spawn(ReplyActor)
        result = await ref.ask("test")
        assert result == "got:test"


@pytest.mark.asyncio
async def test_ask_timeout():
    class SlowActor(Actor):
        async def on_message(self, message):
            await asyncio.sleep(10)

    async with ActorSystem() as system:
        ref = await system.spawn(SlowActor)
        with pytest.raises(asyncio.TimeoutError):
            await ref.ask("x", timeout=0.05)


@pytest.mark.asyncio
async def test_ask_exception_propagated():
    class BoomActor(Actor):
        async def on_message(self, message):
            raise ValueError("boom from ask")

        async def on_error(self, error):
            return SupervisionStrategy.RESTART

    async with ActorSystem() as system:
        ref = await system.spawn(BoomActor)
        with pytest.raises(ValueError, match="boom from ask"):
            await ref.ask("trigger")


# ---------------------------------------------------------------------------
# Supervision strategies from on_error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stop_strategy_halts_actor():
    async with ActorSystem() as system:
        ref = await system.spawn(StopOnErrorActor)
        await ref.send("boom")
        await asyncio.sleep(0.1)
        assert ref.is_alive is False


@pytest.mark.asyncio
async def test_restart_strategy_continues_processing():
    """RESTART keeps the actor alive and processing subsequent messages."""

    class RestartActor(Actor):
        def __init__(self):
            super().__init__()
            self.good_messages: list = []

        async def on_message(self, message):
            if message == "error":
                raise ValueError("oops")
            self.good_messages.append(message)

        async def on_error(self, error):
            return SupervisionStrategy.RESTART

    async with ActorSystem() as system:
        ref = await system.spawn(RestartActor)
        await ref.send("a")
        await ref.send("error")
        await ref.send("b")
        await asyncio.sleep(0.1)
        actor = ref._actor
        assert "a" in actor.good_messages
        assert "b" in actor.good_messages


# ---------------------------------------------------------------------------
# Multiple actors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_actors_independent():
    async with ActorSystem() as system:
        refs = [await system.spawn(AccumulatorActor) for _ in range(3)]
        for i, ref in enumerate(refs):
            await ref.send(i)
        await asyncio.sleep(0.1)
        for i, ref in enumerate(refs):
            assert ref._actor.received == [i]


@pytest.mark.asyncio
async def test_high_throughput_many_messages():
    async with ActorSystem() as system:
        ref = await system.spawn(AccumulatorActor)
        for i in range(200):
            await ref.send(i)
        await asyncio.sleep(0.3)
        assert len(ref._actor.received) == 200


# ---------------------------------------------------------------------------
# Graceful system shutdown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graceful_shutdown_calls_on_stop():
    actors: list[AccumulatorActor] = []

    class TrackingActor(Actor):
        def __init__(self):
            super().__init__()
            self.stopped = False
            actors.append(self)

        async def on_message(self, message):
            pass

        async def on_stop(self):
            self.stopped = True

    async with ActorSystem() as system:
        for _ in range(3):
            await system.spawn(TrackingActor)

    for actor in actors:
        assert actor.stopped is True


@pytest.mark.asyncio
async def test_is_alive_false_after_stop():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        assert ref.is_alive is True
    assert ref.is_alive is False


# ---------------------------------------------------------------------------
# ActorRef.is_alive reflects actor state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stop_via_ref():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        assert ref.is_alive is True
        await ref._actor.stop()
        await asyncio.sleep(0.05)
        assert ref.is_alive is False
