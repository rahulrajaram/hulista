"""Tests for Dispatcher — single dispatch, multiple dispatch, introspection."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from live_dispatch import Dispatcher


# ---------------------------------------------------------------------------
# Basic single-dispatch on type
# ---------------------------------------------------------------------------

def test_single_dispatch_int():
    d = Dispatcher("test")

    @d.register
    def handle_int(x: int) -> str:
        return f"int:{x}"

    assert d(42) == "int:42"


def test_single_dispatch_str():
    d = Dispatcher("test")

    @d.register
    def handle_int(x: int) -> str:
        return f"int:{x}"

    @d.register
    def handle_str(x: str) -> str:
        return f"str:{x}"

    assert d("hello") == "str:hello"
    assert d(7) == "int:7"


def test_single_dispatch_float():
    d = Dispatcher("test")

    @d.register
    def handle_float(x: float) -> str:
        return f"float:{x}"

    assert d(3.14) == "float:3.14"


# ---------------------------------------------------------------------------
# Multiple dispatch on multiple argument types
# ---------------------------------------------------------------------------

def test_multiple_dispatch_two_args():
    d = Dispatcher("multi")

    @d.register
    def handle_int_str(x: int, y: str) -> str:
        return f"int+str:{x},{y}"

    @d.register
    def handle_str_int(x: str, y: int) -> str:
        return f"str+int:{x},{y}"

    assert d(1, "a") == "int+str:1,a"
    assert d("a", 1) == "str+int:a,1"


def test_multiple_dispatch_three_args():
    d = Dispatcher("multi3")

    @d.register
    def handle_three(x: int, y: str, z: float) -> str:
        return f"{x},{y},{z}"

    assert d(1, "b", 2.0) == "1,b,2.0"


def test_multiple_dispatch_kwargs():
    d = Dispatcher("kwargs")

    @d.register
    def handle(x: int, y: str) -> str:
        return f"{x}-{y}"

    assert d(x=10, y="hi") == "10-hi"


def test_dispatch_binds_keyword_only_arguments():
    d = Dispatcher("kwonly")

    @d.register
    def handle(*, x: int, y: str = "hi") -> str:
        return f"{x}-{y}"

    assert d(x=10) == "10-hi"


# ---------------------------------------------------------------------------
# Runtime registration (not just decorator)
# ---------------------------------------------------------------------------

def test_runtime_registration():
    d = Dispatcher("runtime")

    def handle_bytes(x: bytes) -> str:
        return f"bytes:{len(x)}"

    d.register(handle_bytes)
    assert d(b"abc") == "bytes:3"


def test_runtime_registration_with_priority():
    d = Dispatcher("runtime_prio")

    def low_handler(x: int) -> str:
        return "low"

    def high_handler(x: int) -> str:
        return "high"

    d.register(low_handler, priority=0)
    d.register(high_handler, priority=10)

    assert d(5) == "high"


def test_register_rejects_any_annotation():
    d = Dispatcher("bad_any")

    with pytest.raises(TypeError, match="typing.Any"):
        @d.register
        def handle(x: Any) -> str:
            return "bad"


def test_register_accepts_union_annotation():
    """Union annotations are now supported and should not raise."""
    d = Dispatcher("union_ok")

    @d.register
    def handle(x: int | str) -> str:
        return f"union:{x}"

    assert d(1) == "union:1"
    assert d("hi") == "union:hi"


def test_register_rejects_partial_required_annotations():
    d = Dispatcher("partial")

    with pytest.raises(TypeError, match="Untyped required parameter"):
        @d.register
        def handle(x, y: int) -> str:
            return f"{x}-{y}"


def test_register_rejects_unresolved_forward_ref():
    d = Dispatcher("forward")

    with pytest.raises(TypeError, match="could not resolve runtime annotations"):
        @d.register
        def handle(x: "DoesNotExist") -> str:  # noqa: F821
            return "bad"


# ---------------------------------------------------------------------------
# Unregister handler
# ---------------------------------------------------------------------------

def test_unregister():
    d = Dispatcher("unreg")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    @d.register
    def handle_str(x: str) -> str:
        return "str"

    assert d(1) == "int"
    d.unregister(handle_int)
    with pytest.raises(TypeError):
        d(1)


def test_unregister_unknown_does_not_raise():
    d = Dispatcher("unreg2")

    def orphan(x: int) -> str:
        return "orphan"

    # Unregistering something never registered should be a no-op
    d.unregister(orphan)


# ---------------------------------------------------------------------------
# Fallback handler
# ---------------------------------------------------------------------------

def test_fallback_called_when_no_match():
    d = Dispatcher("fallback")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    @d.fallback
    def catch_all(*args, **kwargs) -> str:
        return "fallback"

    assert d("not an int") == "fallback"


def test_fallback_not_called_when_match_exists():
    d = Dispatcher("fallback2")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    @d.fallback
    def catch_all(*args, **kwargs) -> str:
        return "fallback"

    assert d(99) == "int"


# ---------------------------------------------------------------------------
# No-match raises TypeError
# ---------------------------------------------------------------------------

def test_no_match_raises_type_error():
    d = Dispatcher("nomatch")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    with pytest.raises(TypeError, match="No handler in dispatcher 'nomatch'"):
        d("not int")


def test_no_handlers_raises_type_error():
    d = Dispatcher("empty")
    with pytest.raises(TypeError):
        d(42)


# ---------------------------------------------------------------------------
# Handler introspection
# ---------------------------------------------------------------------------

def test_handlers_introspection_empty():
    d = Dispatcher("intro")
    assert d.handlers() == []


def test_handlers_introspection_single():
    d = Dispatcher("intro")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    info = d.handlers()
    assert len(info) == 1
    assert info[0]["function"] == "test_handlers_introspection_single.<locals>.handle_int"
    assert info[0]["types"] == {"x": "int"}
    assert info[0]["priority"] == 0
    assert info[0]["predicate"] is False


def test_handlers_introspection_multiple():
    d = Dispatcher("intro2")

    @d.register(priority=5)
    def handle_int(x: int) -> str:
        return "int"

    @d.register(priority=1)
    def handle_str(x: str) -> str:
        return "str"

    info = d.handlers()
    assert len(info) == 2
    # Sorted by descending priority
    assert info[0]["priority"] == 5
    assert info[1]["priority"] == 1


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

def test_priority_higher_wins():
    d = Dispatcher("prio")

    @d.register(priority=0)
    def low(x: int) -> str:
        return "low"

    @d.register(priority=10)
    def high(x: int) -> str:
        return "high"

    assert d(1) == "high"


def test_priority_equal_first_registered_wins():
    d = Dispatcher("prio_equal")

    @d.register(priority=5)
    def first(x: int) -> str:
        return "first"

    @d.register(priority=5)
    def second(x: int) -> str:
        return "second"

    # With equal priority the sort is stable, first registered comes first
    assert d(1) == "first"


def test_priority_negative():
    d = Dispatcher("prio_neg")

    @d.register(priority=-1)
    def last(x: int) -> str:
        return "last"

    @d.register(priority=0)
    def normal(x: int) -> str:
        return "normal"

    assert d(1) == "normal"


# ---------------------------------------------------------------------------
# Clear all handlers
# ---------------------------------------------------------------------------

def test_clear_removes_all_handlers():
    d = Dispatcher("clear")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    assert len(d.handlers()) == 1
    d.clear()
    assert len(d.handlers()) == 0


def test_clear_removes_fallback():
    d = Dispatcher("clear_fb")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    @d.fallback
    def catch_all(*args, **kwargs) -> str:
        return "fallback"

    d.clear()
    # After clear, fallback is gone so this should raise
    with pytest.raises(TypeError):
        d("something")


def test_clear_then_reregister():
    d = Dispatcher("clear_re")

    @d.register
    def handle_int(x: int) -> str:
        return "old"

    d.clear()

    @d.register
    def handle_int_new(x: int) -> str:
        return "new"

    assert d(1) == "new"


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------

def test_repr():
    d = Dispatcher("my_dispatcher")
    assert "my_dispatcher" in repr(d)
    assert "0" in repr(d)

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    assert "1" in repr(d)


# ---------------------------------------------------------------------------
# call_async
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_async_sync_handler():
    d = Dispatcher("async_test")

    @d.register
    def handle_int(x: int) -> str:
        return f"sync:{x}"

    result = await d.call_async(42)
    assert result == "sync:42"


@pytest.mark.asyncio
async def test_call_async_async_handler():
    d = Dispatcher("async_test")

    @d.register
    async def handle_str(x: str) -> str:
        await asyncio.sleep(0)
        return f"async:{x}"

    result = await d.call_async("hello")
    assert result == "async:hello"


@pytest.mark.asyncio
async def test_call_async_uses_cache():
    """call_async should benefit from the dispatch cache."""
    d = Dispatcher("cached_async")

    @d.register
    def handle_int(x: int) -> str:
        return f"int:{x}"

    # First call populates cache
    result1 = await d.call_async(1)
    assert result1 == "int:1"
    # Second call should hit cache
    result2 = await d.call_async(2)
    assert result2 == "int:2"
    # Verify cache has our type
    key = (int,)
    assert key in d._cache


@pytest.mark.asyncio
async def test_call_async_fallback():
    d = Dispatcher("async_fb")

    @d.fallback
    def catch_all(*args):
        return "fallback"

    result = await d.call_async("anything")
    assert result == "fallback"


@pytest.mark.asyncio
async def test_call_async_no_match():
    d = Dispatcher("async_none")

    @d.register
    def handle_int(x: int):
        return "int"

    with pytest.raises(TypeError, match="No handler"):
        await d.call_async("string_value")


@pytest.mark.asyncio
async def test_call_async_async_fallback():
    d = Dispatcher("async_afb")

    @d.fallback
    async def catch_all(*args):
        await asyncio.sleep(0)
        return "async_fallback"

    result = await d.call_async("anything")
    assert result == "async_fallback"


@pytest.mark.asyncio
async def test_call_async_awaits_future_result():
    d = Dispatcher("async_future")
    loop = asyncio.get_running_loop()

    @d.register
    def handle_int(x: int):
        fut = loop.create_future()
        fut.set_result(f"future:{x}")
        return fut

    result = await d.call_async(4)
    assert result == "future:4"


# ---------------------------------------------------------------------------
# verify_exhaustive
# ---------------------------------------------------------------------------

# Module-level sealed classes for verify_exhaustive tests
# (Must be module-level so get_type_hints can resolve them)

class _Event:
    __sealed__ = True
    __sealed_subclasses__ = set()

class _Click(_Event):
    pass

class _Hover(_Event):
    pass

class _Scroll(_Event):
    pass

_Event.__sealed_subclasses__ = {_Click, _Hover, _Scroll}


def test_verify_exhaustive_full_coverage():
    d = Dispatcher("events")

    @d.register
    def on_click(e: _Click):
        pass

    @d.register
    def on_hover(e: _Hover):
        pass

    @d.register
    def on_scroll(e: _Scroll):
        pass

    # Should not raise
    d.verify_exhaustive(_Event)


def test_verify_exhaustive_missing_handler():
    d = Dispatcher("events")

    @d.register
    def on_click(e: _Click):
        pass

    # Missing Hover and Scroll
    with pytest.raises(TypeError, match="Missing"):
        d.verify_exhaustive(_Event)


def test_verify_exhaustive_not_sealed():
    d = Dispatcher("test")

    class NotSealed:
        pass

    with pytest.raises(TypeError, match="not a sealed class"):
        d.verify_exhaustive(NotSealed)


def test_verify_exhaustive_no_handlers():
    d = Dispatcher("events")

    with pytest.raises(TypeError, match="Missing"):
        d.verify_exhaustive(_Event)


def test_verify_exhaustive_partial_coverage():
    d = Dispatcher("events")

    @d.register
    def on_click(e: _Click):
        pass

    @d.register
    def on_hover(e: _Hover):
        pass

    # Missing Scroll
    with pytest.raises(TypeError, match="Scroll"):
        d.verify_exhaustive(_Event)
