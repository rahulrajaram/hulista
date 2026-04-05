"""Tests for DispatchActor."""
from __future__ import annotations

import asyncio
import sys
import types
import unittest.mock
import pytest

from asyncio_actors.dispatch_actor import DispatchActor
from asyncio_actors.system import ActorSystem


# ---------------------------------------------------------------------------
# Message hierarchy used across most tests
# ---------------------------------------------------------------------------

# We define Ping/Pong as plain classes (no @sealed) for most tests, and use
# sealed variants only where exhaustiveness is tested.

class Msg:
    pass

class Ping(Msg):
    def __init__(self, value: str = "ping") -> None:
        self.value = value

class Pong(Msg):
    def __init__(self, value: str = "pong") -> None:
        self.value = value

class Unknown(Msg):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def spawn(actor_factory):
    """Return an (ActorSystem, ref) context manager for testing."""
    return _SpawnCtx(actor_factory)


class _SpawnCtx:
    def __init__(self, factory):
        self._factory = factory
        self._system = None
        self.ref = None

    async def __aenter__(self):
        self._system = ActorSystem()
        await self._system.__aenter__()
        self.ref = await self._system.spawn(self._factory)
        return self

    async def __aexit__(self, *exc):
        await self._system.__aexit__(*exc)


# ===========================================================================
# 1. Basic dispatch — messages route to correct handler
# ===========================================================================

class BasicActor(DispatchActor):
    @DispatchActor.handle
    async def on_ping(self, msg: Ping) -> str:
        return f"handled-ping:{msg.value}"

    @DispatchActor.handle
    async def on_pong(self, msg: Pong) -> str:
        return f"handled-pong:{msg.value}"


@pytest.mark.asyncio
async def test_basic_dispatch_ping():
    async with ActorSystem() as system:
        ref = await system.spawn(BasicActor)
        result = await ref.ask(Ping("hello"))
        assert result == "handled-ping:hello"


@pytest.mark.asyncio
async def test_basic_dispatch_pong():
    async with ActorSystem() as system:
        ref = await system.spawn(BasicActor)
        result = await ref.ask(Pong("world"))
        assert result == "handled-pong:world"


# ===========================================================================
# 2. Return values work with ask()
# ===========================================================================

class MathActor(DispatchActor):
    @DispatchActor.handle
    async def on_int(self, msg: int) -> int:
        return msg * 2

    @DispatchActor.handle
    async def on_str(self, msg: str) -> str:
        return msg.upper()


@pytest.mark.asyncio
async def test_ask_returns_handler_value():
    async with ActorSystem() as system:
        ref = await system.spawn(MathActor)
        assert await ref.ask(21) == 42
        assert await ref.ask("hello") == "HELLO"


# ===========================================================================
# 3. Exhaustiveness check passes when all sealed subtypes covered
# ===========================================================================

@pytest.mark.asyncio
async def test_exhaustiveness_passes_when_all_covered():
    """Defining a DispatchActor that covers all sealed subtypes should not raise."""
    from sealed_typing._sealed import sealed  # type: ignore[import]

    @sealed
    class Event:
        pass

    class ClickEvent(Event):
        pass

    class HoverEvent(Event):
        pass

    # This class definition should succeed (no TypeError).
    class EventActor(DispatchActor):
        message_type = Event

        @DispatchActor.handle
        async def on_click(self, msg: ClickEvent) -> str:
            return "click"

        @DispatchActor.handle
        async def on_hover(self, msg: HoverEvent) -> str:
            return "hover"

    async with ActorSystem() as system:
        ref = await system.spawn(EventActor)
        assert await ref.ask(ClickEvent()) == "click"
        assert await ref.ask(HoverEvent()) == "hover"


# ===========================================================================
# 4. Exhaustiveness check raises TypeError when a subtype is missing
# ===========================================================================

def test_exhaustiveness_raises_when_subtype_missing():
    from sealed_typing._sealed import sealed  # type: ignore[import]

    @sealed
    class Command:
        pass

    class StartCmd(Command):
        pass

    class StopCmd(Command):  # noqa: F841
        pass

    with pytest.raises(TypeError, match="StopCmd"):
        class IncompleteActor(DispatchActor):
            message_type = Command

            @DispatchActor.handle
            async def on_start(self, msg: StartCmd) -> str:
                return "start"
            # StopCmd intentionally missing


# ===========================================================================
# 5. on_unhandled hook fires for unregistered message types
# ===========================================================================

class UnhandledCapture(DispatchActor):
    def __init__(self):
        super().__init__()
        self.unhandled: list = []

    @DispatchActor.handle
    async def on_ping(self, msg: Ping) -> str:
        return "ping"

    async def on_unhandled(self, message) -> str:
        self.unhandled.append(message)
        return "fallback"


@pytest.mark.asyncio
async def test_on_unhandled_fires_for_unknown_type():
    async with ActorSystem() as system:
        ref = await system.spawn(UnhandledCapture)
        result = await ref.ask(Unknown())
        assert result == "fallback"
        await asyncio.sleep(0.05)
        actor = ref._actor
        assert len(actor.unhandled) == 1
        assert isinstance(actor.unhandled[0], Unknown)


@pytest.mark.asyncio
async def test_default_on_unhandled_raises_type_error():
    """Without overriding on_unhandled, receiving an unmatched msg raises TypeError."""

    class StrictActor(DispatchActor):
        @DispatchActor.handle
        async def on_ping(self, msg: Ping) -> str:
            return "ping"

    async with ActorSystem() as system:
        ref = await system.spawn(StrictActor)
        with pytest.raises(TypeError):
            await ref.ask(Unknown())


# ===========================================================================
# 6. Works without sealed-typing installed (mock import to test)
# ===========================================================================

def test_works_without_sealed_typing(monkeypatch):
    """DispatchActor should still work even if sealed_typing cannot be imported.

    We simulate absence of sealed_typing by making verify_exhaustive raise
    ImportError, which the DispatchActor machinery should swallow silently.
    """
    import live_dispatch._dispatcher as ld  # type: ignore[import]

    # Create a type that looks sealed (has __sealed__ = True) so that
    # __init_subclass__ will attempt to call verify_exhaustive.
    class FakeSealedMsg:
        __sealed__ = True
        __sealed_subclasses__: set = set()

    def patched_verify(self, sealed_base):  # type: ignore[override]
        raise ImportError("mocked: sealed_typing not installed")

    monkeypatch.setattr(ld.Dispatcher, "verify_exhaustive", patched_verify)

    # This should not raise even though verify_exhaustive raises ImportError.
    class SafeActor(DispatchActor):
        message_type = FakeSealedMsg  # type: ignore[assignment]

        @DispatchActor.handle
        async def on_ping(self, msg: Ping) -> str:
            return "ok"

    # The actor class was successfully created.
    assert issubclass(SafeActor, DispatchActor)


# ===========================================================================
# 7. Multiple DispatchActor subclasses don't share handlers
# ===========================================================================

class ActorA(DispatchActor):
    @DispatchActor.handle
    async def on_ping(self, msg: Ping) -> str:
        return "A-ping"


class ActorB(DispatchActor):
    @DispatchActor.handle
    async def on_pong(self, msg: Pong) -> str:
        return "B-pong"


@pytest.mark.asyncio
async def test_actors_do_not_share_handlers():
    async with ActorSystem() as system:
        ref_a = await system.spawn(ActorA)
        ref_b = await system.spawn(ActorB)

        # ActorA handles Ping
        assert await ref_a.ask(Ping()) == "A-ping"
        # ActorA does NOT handle Pong -> on_unhandled -> TypeError
        with pytest.raises(TypeError):
            await ref_a.ask(Pong())

        # ActorB handles Pong
        assert await ref_b.ask(Pong()) == "B-pong"
        # ActorB does NOT handle Ping -> on_unhandled -> TypeError
        with pytest.raises(TypeError):
            await ref_b.ask(Ping())


# ===========================================================================
# 8. Handler with multiple parameters works
# ===========================================================================

# The Dispatcher dispatches on positional arg types.  Our on_message passes
# (self, message).  The handler signature is (self, msg: T).  The wrapper
# strips self from dispatch key.  But what about handlers with extra state
# accessed via self?

class StatefulActor(DispatchActor):
    def __init__(self):
        super().__init__()
        self.count = 0

    @DispatchActor.handle
    async def on_ping(self, msg: Ping) -> str:
        self.count += 1
        return f"count={self.count},value={msg.value}"


@pytest.mark.asyncio
async def test_handler_accesses_self_state():
    async with ActorSystem() as system:
        ref = await system.spawn(StatefulActor)
        r1 = await ref.ask(Ping("a"))
        r2 = await ref.ask(Ping("b"))
        assert r1 == "count=1,value=a"
        assert r2 == "count=2,value=b"


# ===========================================================================
# 9. Inherited handlers work (subclass of DispatchActor subclass)
# ===========================================================================

class BaseDispatch(DispatchActor):
    @DispatchActor.handle
    async def on_ping(self, msg: Ping) -> str:
        return "base-ping"


class DerivedDispatch(BaseDispatch):
    @DispatchActor.handle
    async def on_pong(self, msg: Pong) -> str:
        return "derived-pong"


@pytest.mark.asyncio
async def test_derived_actor_handles_both():
    async with ActorSystem() as system:
        ref = await system.spawn(DerivedDispatch)
        assert await ref.ask(Ping()) == "base-ping"
        assert await ref.ask(Pong()) == "derived-pong"


# ===========================================================================
# 10. Sending messages via send() (fire-and-forget) works
# ===========================================================================

class CollectorActor(DispatchActor):
    def __init__(self):
        super().__init__()
        self.pings: list[str] = []
        self.pongs: list[str] = []

    @DispatchActor.handle
    async def on_ping(self, msg: Ping) -> None:
        self.pings.append(msg.value)

    @DispatchActor.handle
    async def on_pong(self, msg: Pong) -> None:
        self.pongs.append(msg.value)


@pytest.mark.asyncio
async def test_send_fire_and_forget():
    async with ActorSystem() as system:
        ref = await system.spawn(CollectorActor)
        await ref.send(Ping("p1"))
        await ref.send(Pong("q1"))
        await ref.send(Ping("p2"))
        await asyncio.sleep(0.1)
        actor = ref._actor
        assert actor.pings == ["p1", "p2"]
        assert actor.pongs == ["q1"]
