"""Tests for DispatchActor."""
from __future__ import annotations

import asyncio
import builtins
import inspect
import typing
import pytest

import asyncio_actors.dispatch_actor as dispatch_actor_module
from asyncio_actors.dispatch_actor import (
    _HandleMarker,
    _UNRESOLVED,
    _lookup_annotation_name,
    _make_dispatcher,
    _make_handler_wrapper,
    _resolve_annotation_subscript_args,
    _resolve_annotations_at_decoration,
    _resolve_string_annotation,
    DispatchActor,
)
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


@pytest.mark.asyncio
async def test_local_scope_annotations_resolve_without_eval():
    class LocalMsg:
        def __init__(self, value: str) -> None:
            self.value = value

    class LocalActor(DispatchActor):
        @DispatchActor.handle
        async def on_local(self, msg: LocalMsg) -> str:
            return msg.value.upper()

    async with ActorSystem() as system:
        ref = await system.spawn(LocalActor)
        assert await ref.ask(LocalMsg("ok")) == "OK"


def test_unsafe_annotation_expression_is_not_executed(monkeypatch):
    import os

    calls: list[str] = []

    def fake_system(command: str) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(os, "system", fake_system)

    resolved = _resolve_string_annotation("os.system('echo bandit')", {"os": os}, {})
    assert resolved is _UNRESOLVED
    assert calls == []


def test_make_dispatcher_returns_dispatcher_instance():
    dispatcher = _make_dispatcher("test-dispatcher")
    assert dispatcher is not None
    assert type(dispatcher).__name__ == "Dispatcher"


def test_make_dispatcher_returns_none_when_live_dispatch_is_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "live_dispatch._dispatcher":
            raise ImportError("simulated")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert _make_dispatcher("missing") is None


def test_lookup_annotation_name_prefers_local_then_global_then_typing():
    local_value = object()
    global_value = object()

    assert _lookup_annotation_name("None", {}, {}) is type(None)
    assert (
        _lookup_annotation_name("Thing", {"Thing": global_value}, {"Thing": local_value})
        is local_value
    )
    assert _lookup_annotation_name("Thing", {"Thing": global_value}, {}) is global_value
    assert _lookup_annotation_name("Optional", {}, {}) is typing.Optional
    assert _lookup_annotation_name("Missing", {}, {}) is _UNRESOLVED


def test_resolve_string_annotation_handles_supported_forms():
    namespace = {
        "Outer": type("Outer", (), {"Inner": Ping}),
        "Ping": Ping,
        "Pong": Pong,
        "int_value": 1,
        "typing": typing,
    }

    assert _resolve_string_annotation("Ping", {"Ping": Ping}, {}) is Ping
    assert _resolve_string_annotation("Outer.Inner", namespace, {}) is Ping
    assert _resolve_string_annotation("None", {}, {}) is type(None)
    assert _resolve_string_annotation("Ping | Pong", {"Ping": Ping, "Pong": Pong}, {}) == (
        Ping | Pong
    )
    assert _resolve_string_annotation("typing.Union[Ping, Pong]", namespace, {}) == (
        Ping | Pong
    )
    assert _resolve_string_annotation("typing.Optional[Ping]", {"Ping": Ping, "typing": typing}, {}) == (
        Ping | type(None)
    )
    assert _resolve_string_annotation("not valid[", {}, {}) is _UNRESOLVED
    assert _resolve_string_annotation("Missing.Inner", {}, {}) is _UNRESOLVED
    assert _resolve_string_annotation("typing.Union[Ping, Missing]", {"Ping": Ping}, {}) is _UNRESOLVED
    assert _resolve_string_annotation("typing.Optional[int_value]", namespace, {}) is _UNRESOLVED


def test_resolve_annotation_subscript_args_handles_tuple_and_single_values():
    tuple_node = inspect.cleandoc(
        """
        typing.Union[Ping, Pong]
        """
    )
    parsed = dispatch_actor_module.ast.parse(tuple_node, mode="eval").body
    assert isinstance(parsed, dispatch_actor_module.ast.Subscript)
    assert _resolve_annotation_subscript_args(parsed.slice, {"Ping": Ping, "Pong": Pong}, {}) == (
        Ping,
        Pong,
    )

    single_node = dispatch_actor_module.ast.parse("Ping", mode="eval").body
    assert _resolve_annotation_subscript_args(single_node, {"Ping": Ping}, {}) == (Ping,)

    unresolved_tuple = dispatch_actor_module.ast.parse(
        "typing.Union[Ping, Missing]", mode="eval"
    ).body
    assert isinstance(unresolved_tuple, dispatch_actor_module.ast.Subscript)
    assert _resolve_annotation_subscript_args(unresolved_tuple.slice, {"Ping": Ping}, {}) is _UNRESOLVED

    unresolved_single = dispatch_actor_module.ast.parse("Missing", mode="eval").body
    assert _resolve_annotation_subscript_args(unresolved_single, {}, {}) is _UNRESOLVED


def test_resolve_annotations_at_decoration_falls_back_without_eval(monkeypatch):
    monkeypatch.setattr(typing, "get_type_hints", lambda *args, **kwargs: (_ for _ in ()).throw(NameError("nope")))

    class LocalOnly:
        pass

    class FakeFrame:
        def __init__(self, locals_dict: dict[str, object]) -> None:
            self.f_locals = locals_dict

    def fake_getframe(depth: int):
        if depth == 1:
            return FakeFrame({"LocalOnly": LocalOnly, "int": int})
        raise ValueError("done")

    monkeypatch.setattr(dispatch_actor_module.sys, "_getframe", fake_getframe)

    def handler(msg, raw, missing):
        return msg

    handler.__annotations__ = {
        "msg": "LocalOnly",
        "raw": "int",
        "missing": "Missing",
        "return": "LocalOnly",
    }

    hints = _resolve_annotations_at_decoration(handler)
    assert hints == {"msg": LocalOnly, "raw": int}


def test_resolve_annotations_at_decoration_uses_get_type_hints_when_available():
    class LocalOnly:
        pass

    def handler(msg: LocalOnly) -> LocalOnly:
        return msg

    hints = _resolve_annotations_at_decoration(handler)
    assert hints == {"msg": LocalOnly}


def test_handle_marker_descriptor_and_wrapper_behaviour():
    class MarkerActor:
        async def handle_ping(self, msg: Ping) -> str:
            return msg.value

    marker = _HandleMarker(MarkerActor.handle_ping)
    actor = MarkerActor()

    assert marker.__get__(None, MarkerActor) is marker
    bound = marker.__get__(actor, MarkerActor)
    assert inspect.ismethod(bound)


@pytest.mark.asyncio
async def test_make_handler_wrapper_preserves_signature_and_annotations():
    class WrapperActor:
        async def handle_ping(self, msg: Ping, suffix: str = "!") -> str:
            return f"{msg.value}{suffix}"

    wrapper = _make_handler_wrapper(WrapperActor.handle_ping, {"msg": Ping, "suffix": str})
    actor = WrapperActor()

    assert wrapper.__annotations__ == {"self": object, "msg": Ping, "suffix": str}
    assert inspect.signature(wrapper) == inspect.signature(WrapperActor.handle_ping)
    assert wrapper.__module__ == "asyncio_actors.dispatch_actor"
    assert await wrapper(actor, Ping("ok"), suffix="?") == "ok?"


@pytest.mark.asyncio
async def test_on_message_falls_back_when_dispatcher_missing(monkeypatch):
    monkeypatch.setattr(dispatch_actor_module, "_make_dispatcher", lambda name: None)

    class MissingDispatcherActor(DispatchActor):
        async def on_unhandled(self, message) -> str:
            return f"missing:{message}"

    actor = MissingDispatcherActor()
    assert MissingDispatcherActor._dispatcher is None
    assert await actor.on_message("payload") == "missing:payload"


@pytest.mark.asyncio
async def test_on_message_falls_back_when_dispatcher_raises_type_error():
    class RaisingDispatcher:
        async def call_async(self, actor, message):
            raise TypeError("no match")

    class RaisingActor(DispatchActor):
        async def on_unhandled(self, message) -> str:
            return f"fallback:{message}"

    RaisingActor._dispatcher = RaisingDispatcher()
    actor = RaisingActor()
    assert await actor.on_message("payload") == "fallback:payload"


def test_init_subclass_registers_handlers_from_base_classes():
    class TrackingDispatcher:
        def __init__(self):
            self.registered: list[typing.Callable[..., typing.Any]] = []
            self.verified = None

        def register(self, fn):
            self.registered.append(fn)

        def verify_exhaustive(self, mt):
            self.verified = mt

    dispatcher = TrackingDispatcher()
    original = dispatch_actor_module._make_dispatcher
    dispatch_actor_module._make_dispatcher = lambda name: dispatcher
    try:
        class BaseTracked(DispatchActor):
            @DispatchActor.handle
            async def on_ping(self, msg: Ping) -> str:
                return "ping"

        class DerivedTracked(BaseTracked):
            message_type = type("NotSealed", (), {"__sealed__": False})

            @DispatchActor.handle
            async def on_pong(self, msg: Pong) -> str:
                return "pong"

    finally:
        dispatch_actor_module._make_dispatcher = original

    names = [fn.__name__ for fn in dispatcher.registered]
    assert names == ["on_ping", "on_ping", "on_pong"]
    assert dispatcher.verified is None


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
