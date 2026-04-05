"""Tests for versioned dispatch tables with rollback support."""
from __future__ import annotations

import pytest
from live_dispatch import Dispatcher, predicate, versioned


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_dispatcher_with_int_handler(name="d"):
    d = Dispatcher(name)

    @d.register
    def handle_int(x: int) -> str:
        return "original"

    return d


# ---------------------------------------------------------------------------
# Versioned context saves and restores handlers
# ---------------------------------------------------------------------------

def test_versioned_context_is_context_manager():
    d = make_dispatcher_with_int_handler()
    with versioned(d) as v:
        assert v is not None


def test_versioned_saves_snapshot_on_enter():
    d = make_dispatcher_with_int_handler()
    original_count = len(d.handlers())

    with versioned(d) as v:
        assert v._snapshot is not None
        assert len(v._snapshot["handlers"]) == original_count


# ---------------------------------------------------------------------------
# Rollback restores previous state
# ---------------------------------------------------------------------------

def test_rollback_removes_added_handler():
    d = make_dispatcher_with_int_handler()

    with versioned(d) as v:
        @d.register
        def handle_str(x: str) -> str:
            return "new"

        assert d("hi") == "new"
        v.rollback()

    # After rollback, str handler should be gone
    with pytest.raises(TypeError):
        d("hi")


def test_rollback_preserves_original_handlers():
    d = make_dispatcher_with_int_handler()

    with versioned(d) as v:
        @d.register
        def extra(x: str) -> str:
            return "extra"

        v.rollback()

    # Original int handler still works
    assert d(5) == "original"


def test_rollback_after_clear():
    d = make_dispatcher_with_int_handler()

    with versioned(d) as v:
        d.clear()
        assert len(d.handlers()) == 0

        v.rollback()

    # After rollback, original handler is back
    assert d(1) == "original"


def test_rollback_restores_fallback():
    d = make_dispatcher_with_int_handler()

    @d.fallback
    def original_fallback(*args):
        return "fallback"

    with versioned(d) as v:
        d.clear()
        v.rollback()

    assert d("hi") == "fallback"


def test_rollback_to_empty_dispatcher():
    d = Dispatcher("empty")
    assert len(d.handlers()) == 0

    with versioned(d) as v:
        @d.register
        def handle_int(x: int) -> str:
            return "int"

        assert len(d.handlers()) == 1
        v.rollback()

    assert len(d.handlers()) == 0


# ---------------------------------------------------------------------------
# Without rollback, new handlers persist
# ---------------------------------------------------------------------------

def test_no_rollback_handlers_persist():
    d = make_dispatcher_with_int_handler()

    with versioned(d):
        @d.register
        def handle_str(x: str) -> str:
            return "str"

    # No rollback was called; str handler should still be registered
    assert d("hi") == "str"


def test_no_rollback_on_exception():
    d = make_dispatcher_with_int_handler()

    try:
        with versioned(d):
            @d.register
            def handle_str(x: str) -> str:
                return "str"

            raise ValueError("something went wrong")
    except ValueError:
        pass

    # Without explicit rollback, handler persists even after exception
    assert d("hi") == "str"


# ---------------------------------------------------------------------------
# Nested versioned contexts
# ---------------------------------------------------------------------------

def test_nested_versioned_contexts_independent_snapshots():
    d = Dispatcher("nested")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    with versioned(d) as outer:
        @d.register
        def handle_str(x: str) -> str:
            return "str"

        assert len(d.handlers()) == 2

        with versioned(d) as inner:
            @d.register
            def handle_bytes(x: bytes) -> str:
                return "bytes"

            assert len(d.handlers()) == 3
            inner.rollback()

        # Inner rollback removed bytes handler but str handler remains
        assert len(d.handlers()) == 2
        assert d("hi") == "str"

        outer.rollback()

    # Outer rollback restored to just int handler
    assert len(d.handlers()) == 1
    assert d(1) == "int"


def test_nested_outer_rollback_after_inner_rollback():
    d = Dispatcher("nested2")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    with versioned(d) as outer:
        @d.register
        def handle_str(x: str) -> str:
            return "str"

        with versioned(d) as inner:
            @d.register
            def handle_bytes(x: bytes) -> str:
                return "bytes"

            inner.rollback()
            # After inner rollback, we're back to int + str
            assert len(d.handlers()) == 2

        # Still at int + str after inner context exits without rollback
        assert len(d.handlers()) == 2
        outer.rollback()

    # Outer rollback puts us back to just int
    assert len(d.handlers()) == 1


def test_rollback_is_idempotent():
    d = make_dispatcher_with_int_handler()

    with versioned(d) as v:
        @d.register
        def handle_str(x: str) -> str:
            return "str"

        v.rollback()
        # Second rollback should restore to same snapshot (not double-rollback)
        v.rollback()

    assert len(d.handlers()) == 1
    assert d(1) == "original"


def test_rollback_restores_predicate_cache_state():
    d = Dispatcher("predicates")

    @d.register(priority=1)
    def handle_int(x: int) -> str:
        return "plain"

    assert d._has_predicates is False

    with versioned(d) as v:
        @d.register(priority=2)
        @predicate(lambda x: x % 2 == 0)
        def handle_even(x: int) -> str:
            return "even"

        assert d._has_predicates is True
        v.rollback()

    assert d._has_predicates is False
