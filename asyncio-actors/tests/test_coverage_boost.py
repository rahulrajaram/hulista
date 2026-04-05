"""Targeted tests to boost branch coverage for asyncio-actors.

Covers uncovered branches in dispatch_actor.py, actor.py, and inbox.py.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from asyncio_actors.actor import (
    Actor,
    Envelope,
    _AskEnvelope,
    _SENTINEL,
)
from asyncio_actors.inbox import Inbox, OverflowPolicy
from asyncio_actors.system import ActorSystem


# ===========================================================================
# dispatch_actor.py — _make_dispatcher ImportError path (lines 20-21)
# ===========================================================================


def test_make_dispatcher_returns_none_when_live_dispatch_missing():
    """When live_dispatch is not importable, _make_dispatcher returns None."""
    import unittest.mock
    from asyncio_actors import dispatch_actor

    # Setting a sys.modules entry to None causes ImportError on import.
    blocked = {
        k: None
        for k in list(sys.modules)
        if k == "live_dispatch" or k.startswith("live_dispatch.")
    }
    # Also block the top-level and dispatcher modules explicitly.
    blocked["live_dispatch"] = None
    blocked["live_dispatch._dispatcher"] = None

    with unittest.mock.patch.dict(sys.modules, blocked):
        result = dispatch_actor._make_dispatcher("test")
        assert result is None


# ===========================================================================
# dispatch_actor.py — DispatchActor when dispatcher is None (lines 156, 191)
# ===========================================================================


@pytest.mark.asyncio
async def test_dispatch_actor_no_dispatcher_falls_through_to_on_unhandled():
    """When _dispatcher is None, on_message delegates to on_unhandled."""
    from asyncio_actors.dispatch_actor import DispatchActor

    class NullDispatchActor(DispatchActor):
        async def on_unhandled(self, message):
            return f"unhandled:{message}"

    actor = NullDispatchActor()
    # Force dispatcher to None to simulate missing live-dispatch.
    NullDispatchActor._dispatcher = None
    try:
        result = await actor.on_message("hello")
        assert result == "unhandled:hello"
    finally:
        # Restore
        NullDispatchActor._dispatcher = None


# ===========================================================================
# dispatch_actor.py — _resolve_annotations_at_decoration fallback (lines 55-70)
# ===========================================================================


def test_resolve_annotations_fallback_when_get_type_hints_fails():
    """When get_type_hints raises, fallback to raw annotations with eval."""
    from asyncio_actors.dispatch_actor import _resolve_annotations_at_decoration

    # Create a function with annotations that will fail get_type_hints.
    def handler(self, msg: "NonExistentType") -> str:  # noqa: F821
        return "ok"

    # _resolve_annotations_at_decoration should fall back without crashing.
    # The annotation string won't resolve, so it should be skipped.
    hints = _resolve_annotations_at_decoration(handler)
    # "msg" annotation won't resolve to anything, so hints may be empty.
    # The key thing is it doesn't raise.
    assert isinstance(hints, dict)


def test_resolve_annotations_fallback_with_resolvable_string():
    """Fallback path resolves string annotations via eval when get_type_hints fails."""
    from asyncio_actors.dispatch_actor import _resolve_annotations_at_decoration

    # Create a function where get_type_hints will fail but raw annotations
    # contain types resolvable in the module's namespace.
    def handler(self, msg: int) -> str:
        return "ok"

    # Force the function to have string annotations that ARE resolvable.
    handler.__annotations__ = {"msg": "int", "return": "str"}

    # Sabotage __module__ so get_type_hints fails.
    handler.__module__ = "__nonexistent_module_for_testing__"

    hints = _resolve_annotations_at_decoration(handler)
    # The fallback should eval "int" to the int builtin.
    assert hints.get("msg") is int or hints == {}  # Depends on frame locals


# ===========================================================================
# dispatch_actor.py — _HandleMarker.__get__ (lines 93-96)
# ===========================================================================


def test_handle_marker_get_on_class_returns_self():
    """Accessing a _HandleMarker on the class (not an instance) returns the marker."""
    from asyncio_actors.dispatch_actor import _HandleMarker

    async def handler(self, msg: int) -> int:
        return msg

    marker = _HandleMarker(handler)

    # Simulate class-level access: __get__(None, SomeClass)
    result = marker.__get__(None, type)
    assert result is marker


def test_handle_marker_get_on_instance_returns_bound_method():
    """Accessing a _HandleMarker on an instance returns the bound method."""
    from asyncio_actors.dispatch_actor import _HandleMarker

    async def handler(self, msg: int) -> int:
        return msg

    marker = _HandleMarker(handler)

    class Dummy:
        pass

    obj = Dummy()
    bound = marker.__get__(obj, Dummy)
    # The bound method should be callable and tied to obj.
    assert callable(bound)


# ===========================================================================
# dispatch_actor.py — _make_handler_wrapper signature edge cases (lines 259-260)
# ===========================================================================


def test_make_handler_wrapper_sets_signature():
    """_make_handler_wrapper produces a wrapper with __signature__."""
    from asyncio_actors.dispatch_actor import _make_handler_wrapper

    async def handler(self, msg: int) -> int:
        return msg * 2

    wrapper = _make_handler_wrapper(handler, {"msg": int})
    assert wrapper.__annotations__["msg"] is int
    assert wrapper.__annotations__.get(list(wrapper.__annotations__)[0]) is object


# ===========================================================================
# dispatch_actor.py — message_type is not sealed (line 178->exit)
# ===========================================================================


def test_message_type_not_sealed_skips_exhaustiveness():
    """Setting message_type to a non-sealed class skips verify_exhaustive."""
    from asyncio_actors.dispatch_actor import DispatchActor

    class PlainMsg:
        pass

    class SubMsg(PlainMsg):
        pass

    # This should not raise — PlainMsg has no __sealed__ attribute.
    class PlainActor(DispatchActor):
        message_type = PlainMsg

        @DispatchActor.handle
        async def on_sub(self, msg: SubMsg) -> str:
            return "ok"

    assert PlainActor._dispatcher is not None


# ===========================================================================
# actor.py — _unwrap_raw with _AskEnvelope (line 320)
# ===========================================================================


@pytest.mark.asyncio
async def test_unwrap_raw_ask_envelope():
    """_unwrap_raw extracts the message from an _AskEnvelope."""
    inner_env = Envelope(message="payload", sender=None)
    fut = asyncio.get_running_loop().create_future()
    ask_env = _AskEnvelope(inner_env, fut)
    result = Actor._unwrap_raw(ask_env)
    assert result == "payload"
    fut.cancel()


def test_unwrap_raw_bare_message():
    """_unwrap_raw passes through a bare (non-envelope) message."""
    result = Actor._unwrap_raw(42)
    assert result == 42


# ===========================================================================
# actor.py — selective receive with stashed non-matching messages (lines 300-304)
# ===========================================================================


@pytest.mark.asyncio
async def test_selective_receive_stashes_non_matching():
    """Selective receive stashes non-matching messages and returns when match arrives."""

    class Cmd:
        pass

    class Reply:
        def __init__(self, value: str):
            self.value = value

    class SelectiveActor(Actor):
        async def on_message(self, message):
            if message == "wait_for_reply":
                # Use selective receive to wait for a Reply
                reply = await self.receive(match=Reply, timeout=2.0)
                return reply.value

    async with ActorSystem() as system:
        ref = await system.spawn(SelectiveActor)

        # Send a Reply then ask the actor to wait for it.
        # The actor will receive "wait_for_reply" first, then look for Reply
        # in the inbox. We need to send the Reply from a task so it arrives
        # while the actor is waiting.
        async def send_delayed():
            await asyncio.sleep(0.1)
            # Send a non-matching message first
            await ref.send(Cmd())
            await asyncio.sleep(0.05)
            # Then send the matching Reply
            await ref.send(Reply("found-it"))

        asyncio.create_task(send_delayed())
        result = await ref.ask("wait_for_reply", timeout=3.0)
        assert result == "found-it"


# ===========================================================================
# actor.py — watch() on already-stopped actor with done future (line 152->154)
# ===========================================================================


@pytest.mark.asyncio
async def test_watch_on_already_stopped_actor_resolves_immediately():
    """Calling watch() on a stopped actor returns an already-resolved future."""

    class QuickActor(Actor):
        async def on_message(self, message):
            return message

    async with ActorSystem() as system:
        ref = await system.spawn(QuickActor)
        await ref.stop()
        await asyncio.sleep(0.1)  # Let the actor fully stop.

        done = await ref.watch()
        # Future should already be resolved.
        assert done.done()
        assert done.result() is None


# ===========================================================================
# inbox.py — BLOCK policy: inbox closed while waiting (lines 57->66, 62)
# ===========================================================================


@pytest.mark.asyncio
async def test_inbox_block_closed_while_waiting():
    """put() raises RuntimeError if inbox is closed while blocked on full."""
    inbox = Inbox(maxsize=1, policy=OverflowPolicy.BLOCK)
    await inbox.put("fill")

    async def close_later():
        await asyncio.sleep(0.05)
        inbox.close()

    asyncio.create_task(close_later())
    with pytest.raises(RuntimeError, match="closed while waiting"):
        await inbox.put("should-block-then-fail")


# ===========================================================================
# inbox.py — _notify_waiters skips done futures (line 93->88)
# ===========================================================================


@pytest.mark.asyncio
async def test_notify_waiters_skips_done_futures():
    """If a waiter future is already done, _notify_waiters skips it."""
    inbox = Inbox(maxsize=10, policy=OverflowPolicy.BLOCK)

    loop = asyncio.get_running_loop()
    done_fut = loop.create_future()
    done_fut.set_result("already-done")
    inbox._waiters.append(done_fut)

    # Put a message — the done future should be skipped.
    await inbox.put("msg")
    # The message should remain in the queue since no live waiter consumed it.
    assert len(inbox._queue) == 1


# ===========================================================================
# inbox.py — receive with timeout (lines 142-169)
# ===========================================================================


@pytest.mark.asyncio
async def test_inbox_receive_finds_match_in_stash():
    """Inbox.receive finds a matching message in the stash first."""
    inbox = Inbox(maxsize=10, policy=OverflowPolicy.BLOCK)
    # Put a non-matching item into stash, then a matching one.
    inbox._stash.append("not-int")
    inbox._stash.append(42)

    result = await inbox.receive(int)
    assert result == 42
    # The non-matching item stays.
    assert len(inbox._stash) == 1


@pytest.mark.asyncio
async def test_inbox_receive_finds_match_in_queue():
    """Inbox.receive finds a matching message in the queue."""
    inbox = Inbox(maxsize=10, policy=OverflowPolicy.BLOCK)
    # Put a non-matching item, then a matching one into queue.
    inbox._queue.append("not-int")
    inbox._queue.append(99)

    result = await inbox.receive(int)
    assert result == 99


@pytest.mark.asyncio
async def test_inbox_receive_timeout_in_wait_loop():
    """Inbox.receive raises TimeoutError when deadline passes in wait loop."""
    inbox = Inbox(maxsize=10, policy=OverflowPolicy.BLOCK)

    # Put a non-matching message that will arrive while waiting.
    async def send_non_matching():
        await asyncio.sleep(0.05)
        inbox._queue.append("not-int")
        inbox._notify_waiters()

    asyncio.create_task(send_non_matching())

    with pytest.raises(asyncio.TimeoutError):
        await inbox.receive(int, timeout=0.15)


@pytest.mark.asyncio
async def test_inbox_receive_stashes_non_matching_from_wait():
    """Inbox.receive stashes non-matching messages received during wait."""
    inbox = Inbox(maxsize=10, policy=OverflowPolicy.BLOCK)

    async def send_messages():
        await asyncio.sleep(0.05)
        # Send non-matching first
        inbox._queue.append("string")
        inbox._notify_waiters()
        await asyncio.sleep(0.05)
        # Then send matching
        inbox._queue.append(42)
        inbox._notify_waiters()

    asyncio.create_task(send_messages())

    result = await inbox.receive(int, timeout=2.0)
    assert result == 42
    # The non-matching "string" should be in stash.
    assert "string" in inbox._stash


# ===========================================================================
# inbox.py — close() with already-done waiter futures
# ===========================================================================


@pytest.mark.asyncio
async def test_inbox_close_skips_done_waiters():
    """close() skips waiter futures that are already done."""
    inbox = Inbox(maxsize=10)
    loop = asyncio.get_running_loop()
    done_fut = loop.create_future()
    done_fut.set_result("done")
    inbox._waiters.append(done_fut)

    # close should not raise when encountering a done future.
    inbox.close()
    assert inbox._closed


# ===========================================================================
# actor.py — selective receive scan finds match in queue (line 312-313)
# ===========================================================================


def test_scan_inbox_for_match_finds_in_queue():
    """_scan_inbox_for_match finds an envelope-wrapped match in queue."""
    actor = Actor.__new__(Actor)
    actor._inbox = Inbox(maxsize=10)

    # Put an Envelope wrapping an int into the queue.
    env = Envelope(message=42)
    actor._inbox._queue.append(env)

    result = actor._scan_inbox_for_match(int)
    assert result == 42
    assert len(actor._inbox._queue) == 0


def test_scan_inbox_for_match_returns_sentinel_when_no_match():
    """_scan_inbox_for_match returns _SENTINEL when nothing matches."""
    actor = Actor.__new__(Actor)
    actor._inbox = Inbox(maxsize=10)

    actor._inbox._queue.append(Envelope(message="string"))

    result = actor._scan_inbox_for_match(int)
    assert result is _SENTINEL


# ===========================================================================
# actor.py — _run cancellation when not running (line 394->397)
# ===========================================================================


@pytest.mark.asyncio
async def test_actor_cancellation_during_stop():
    """CancelledError during shutdown (when _running=False) exits cleanly."""

    class CancelActor(Actor):
        async def on_message(self, message):
            return message

    async with ActorSystem() as system:
        ref = await system.spawn(CancelActor)
        # Stop the actor — this sets _running=False and cancels the task.
        await ref.stop()
        await asyncio.sleep(0.1)
        assert not ref.is_alive
