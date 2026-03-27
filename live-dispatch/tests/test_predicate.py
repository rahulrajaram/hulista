"""Tests for predicate dispatch."""
from __future__ import annotations

import pytest
from live_dispatch import Dispatcher, predicate


# ---------------------------------------------------------------------------
# Predicate decorator adds __dispatch_predicate__
# ---------------------------------------------------------------------------

def test_predicate_sets_attribute():
    cond = lambda x: x > 0

    @predicate(cond)
    def my_func(x: int) -> str:
        return "positive"

    assert hasattr(my_func, '__dispatch_predicate__')
    assert my_func.__dispatch_predicate__ is cond


def test_predicate_callable_preserved():
    @predicate(lambda x: isinstance(x, int) and x % 2 == 0)
    def even_handler(x: int) -> str:
        return "even"

    assert even_handler.__dispatch_predicate__(4) is True
    assert even_handler.__dispatch_predicate__(3) is False


# ---------------------------------------------------------------------------
# Predicate-based dispatch selects correct handler
# ---------------------------------------------------------------------------

def test_predicate_dispatch_selects_matching():
    d = Dispatcher("pred")

    @d.register(priority=1)
    @predicate(lambda x: x > 10)
    def handle_large(x: int) -> str:
        return "large"

    @d.register(priority=0)
    def handle_any(x: int) -> str:
        return "any"

    assert d(20) == "large"
    assert d(5) == "any"


def test_predicate_dispatch_string_value():
    d = Dispatcher("pred_str")

    @d.register(priority=1)
    @predicate(lambda s: s.startswith("hello"))
    def handle_greeting(s: str) -> str:
        return "greeting"

    @d.register(priority=0)
    def handle_other(s: str) -> str:
        return "other"

    assert d("hello world") == "greeting"
    assert d("goodbye") == "other"


# ---------------------------------------------------------------------------
# Predicate that returns False skips handler
# ---------------------------------------------------------------------------

def test_predicate_false_skips_handler():
    d = Dispatcher("pred_skip")

    @d.register(priority=2)
    @predicate(lambda x: False)
    def never_matches(x: int) -> str:
        return "never"

    @d.register(priority=1)
    def always_matches(x: int) -> str:
        return "always"

    assert d(99) == "always"


def test_predicate_exception_in_condition_skips():
    d = Dispatcher("pred_exc")

    @d.register(priority=2)
    @predicate(lambda x: x.nonexistent_attr > 0)  # will raise AttributeError
    def risky(x: int) -> str:
        return "risky"

    @d.register(priority=1)
    def safe(x: int) -> str:
        return "safe"

    assert d(5) == "safe"


# ---------------------------------------------------------------------------
# Multiple predicates with priority
# ---------------------------------------------------------------------------

def test_multiple_predicates_priority_ordering():
    d = Dispatcher("pred_multi")

    @d.register(priority=10)
    @predicate(lambda x: x > 100)
    def handle_huge(x: int) -> str:
        return "huge"

    @d.register(priority=5)
    @predicate(lambda x: x > 50)
    def handle_medium(x: int) -> str:
        return "medium"

    @d.register(priority=0)
    def handle_small(x: int) -> str:
        return "small"

    assert d(200) == "huge"
    assert d(75) == "medium"
    assert d(10) == "small"


def test_predicate_with_type_and_predicate():
    d = Dispatcher("pred_type")

    @d.register(priority=1)
    @predicate(lambda x: x < 0)
    def handle_negative(x: int) -> str:
        return "negative"

    @d.register(priority=0)
    def handle_int(x: int) -> str:
        return "int"

    assert d(-5) == "negative"
    assert d(5) == "int"
    # String should not match either int handler
    with pytest.raises(TypeError):
        d("not an int")


def test_predicate_on_untyped_handler():
    d = Dispatcher("pred_untyped")

    @d.register(priority=1)
    @predicate(lambda x: x == 42)
    def handle_42(x) -> str:
        return "the answer"

    @d.register(priority=0)
    @predicate(lambda x: True)
    def handle_any(x) -> str:
        return "anything"

    assert d(42) == "the answer"
    assert d(7) == "anything"


def test_no_predicate_match_raises():
    d = Dispatcher("pred_none")

    @d.register
    @predicate(lambda x: x > 1000)
    def handle_huge(x: int) -> str:
        return "huge"

    with pytest.raises(TypeError):
        d(1)
