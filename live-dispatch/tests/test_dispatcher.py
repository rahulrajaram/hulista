"""Tests for Dispatcher — single dispatch, multiple dispatch, introspection."""
from __future__ import annotations

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
