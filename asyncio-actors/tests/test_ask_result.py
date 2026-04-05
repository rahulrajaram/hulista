"""Tests for ActorRef.ask_result() — Result-returning variant of ask()."""
from __future__ import annotations

import asyncio
import sys
import pytest

from asyncio_actors.actor import Actor, _get_result_types
from asyncio_actors.system import ActorSystem
from asyncio_actors.supervision import SupervisionStrategy
from fp_combinators import Ok, Err


# ---------------------------------------------------------------------------
# Helper actors
# ---------------------------------------------------------------------------

class EchoActor(Actor):
    """Returns the message unchanged."""

    async def on_message(self, message):
        return message


class SlowActor(Actor):
    """Never replies — used to trigger timeouts."""

    async def on_message(self, message):
        await asyncio.sleep(60)


class BoomActor(Actor):
    """Raises a ValueError for every message."""

    async def on_message(self, message):
        raise ValueError("boom from actor")

    async def on_error(self, error):
        # Keep the actor alive so we can send multiple messages.
        return SupervisionStrategy.RESTART


# ---------------------------------------------------------------------------
# ask_result — success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_result_ok_on_success():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        result = await ref.ask_result("hello")

    assert isinstance(result, Ok)
    assert result.value == "hello"


@pytest.mark.asyncio
async def test_ask_result_ok_value_unwrappable():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        result = await ref.ask_result(42)

    assert result.unwrap() == 42


# ---------------------------------------------------------------------------
# ask_result — timeout path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_result_err_on_timeout():
    async with ActorSystem() as system:
        ref = await system.spawn(SlowActor)
        result = await ref.ask_result("tick", timeout=0.05)

    assert isinstance(result, Err)
    assert isinstance(result.error, TimeoutError)


@pytest.mark.asyncio
async def test_ask_result_timeout_message_contains_duration():
    async with ActorSystem() as system:
        ref = await system.spawn(SlowActor)
        result = await ref.ask_result("tick", timeout=0.05)

    assert "0.05" in str(result.error)


# ---------------------------------------------------------------------------
# ask_result — actor exception path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_result_err_on_actor_exception():
    async with ActorSystem() as system:
        ref = await system.spawn(BoomActor)
        result = await ref.ask_result("trigger")

    assert isinstance(result, Err)
    assert isinstance(result.error, ValueError)
    assert "boom from actor" in str(result.error)


@pytest.mark.asyncio
async def test_ask_result_err_preserves_exception_type():
    class TypedBoomActor(Actor):
        async def on_message(self, message):
            raise KeyError("missing-key")

        async def on_error(self, error):
            return SupervisionStrategy.RESTART

    async with ActorSystem() as system:
        ref = await system.spawn(TypedBoomActor)
        result = await ref.ask_result("trigger")

    assert isinstance(result.error, KeyError)


# ---------------------------------------------------------------------------
# ask_result — chaining / functional operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_result_map_on_ok():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        result = await ref.ask_result(10)

    doubled = result.map(lambda x: x * 2)
    assert doubled == Ok(20)


@pytest.mark.asyncio
async def test_ask_result_map_not_called_on_err():
    async with ActorSystem() as system:
        ref = await system.spawn(BoomActor)
        result = await ref.ask_result("trigger")

    mapped = result.map(lambda x: x * 2)
    assert mapped.is_err()


@pytest.mark.asyncio
async def test_ask_result_and_then_chaining():
    async with ActorSystem() as system:
        ref = await system.spawn(EchoActor)
        result = await ref.ask_result("base")

    chained = result.and_then(lambda v: Ok(v + "-chained"))
    assert chained == Ok("base-chained")


@pytest.mark.asyncio
async def test_ask_result_or_else_on_err():
    async with ActorSystem() as system:
        ref = await system.spawn(SlowActor)
        result = await ref.ask_result("tick", timeout=0.05)

    recovered = result.or_else(lambda _: Ok("default"))
    assert recovered == Ok("default")


@pytest.mark.asyncio
async def test_ask_result_is_ok_and_is_err_helpers():
    async with ActorSystem() as system:
        ref_echo = await system.spawn(EchoActor)
        ref_slow = await system.spawn(SlowActor)

        ok_result = await ref_echo.ask_result("ping")
        err_result = await ref_slow.ask_result("ping", timeout=0.05)

    assert ok_result.is_ok() is True
    assert ok_result.is_err() is False
    assert err_result.is_ok() is False
    assert err_result.is_err() is True


@pytest.mark.asyncio
async def test_ask_result_unwrap_or_on_err():
    async with ActorSystem() as system:
        ref = await system.spawn(SlowActor)
        result = await ref.ask_result("tick", timeout=0.05)

    assert result.unwrap_or("fallback") == "fallback"


# ---------------------------------------------------------------------------
# ask_result — existing ask() is unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_still_raises_on_timeout():
    async with ActorSystem() as system:
        ref = await system.spawn(SlowActor)
        with pytest.raises(asyncio.TimeoutError):
            await ref.ask("tick", timeout=0.05)


@pytest.mark.asyncio
async def test_ask_still_raises_on_actor_exception():
    async with ActorSystem() as system:
        ref = await system.spawn(BoomActor)
        with pytest.raises(ValueError, match="boom from actor"):
            await ref.ask("trigger")


# ---------------------------------------------------------------------------
# ImportError path — fp-combinators not installed
# ---------------------------------------------------------------------------

def test_get_result_types_import_error(monkeypatch):
    """_get_result_types() raises ImportError with a clear message when
    fp-combinators is unavailable."""

    # Temporarily hide fp_combinators from sys.modules.
    original = sys.modules.copy()
    # Remove the package and all sub-modules so the import fails.
    for key in list(sys.modules):
        if key == "fp_combinators" or key.startswith("fp_combinators."):
            sys.modules[key] = None  # type: ignore[assignment]

    # Also block the import at finder level.
    class _BlockFinder:
        def find_module(self, name, path=None):
            if name == "fp_combinators" or name.startswith("fp_combinators."):
                return self
            return None

        def load_module(self, name):
            raise ImportError(f"Mocked: {name} not available")

    blocker = _BlockFinder()
    sys.meta_path.insert(0, blocker)
    try:
        with pytest.raises(ImportError, match="fp-combinators"):
            _get_result_types()
    finally:
        sys.meta_path.remove(blocker)
        # Restore original modules.
        for key in list(sys.modules):
            if key not in original:
                del sys.modules[key]
        for key, val in original.items():
            sys.modules[key] = val
