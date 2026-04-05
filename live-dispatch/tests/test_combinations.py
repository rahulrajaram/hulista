"""Tests for CLOS-inspired method combinations on Dispatcher."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from live_dispatch import CombinationTraceEntry, Dispatcher


# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------

class Animal:
    pass

class Dog(Animal):
    pass

class Cat(Animal):
    pass


# ---------------------------------------------------------------------------
# Basic before/after/around execution order
# ---------------------------------------------------------------------------

def test_before_runs_before_primary():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        log.append("primary")
        return "done"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        log.append("before")

    result = d(Animal())
    assert result == "done"
    assert log == ["before", "primary"]


def test_after_runs_after_primary():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        log.append("primary")
        return "done"

    @d.after(Animal)
    def post(x: Animal) -> None:
        log.append("after")

    result = d(Animal())
    assert result == "done"
    assert log == ["primary", "after"]


def test_before_after_around_order():
    """Full order: around_enter -> before -> primary -> after -> around_exit."""
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        log.append("primary")
        return "done"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        log.append("before")

    @d.after(Animal)
    def post(x: Animal) -> None:
        log.append("after")

    @d.around(Animal)
    def wrap(proceed, x: Animal) -> str:
        log.append("around_enter")
        result = proceed(x)
        log.append("around_exit")
        return result

    result = d(Animal())
    assert result == "done"
    assert log == ["around_enter", "before", "primary", "after", "around_exit"]


# ---------------------------------------------------------------------------
# Multiple before advisors run in registration order
# ---------------------------------------------------------------------------

def test_multiple_before_registration_order():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        return "primary"

    @d.before(Animal)
    def before1(x: Animal) -> None:
        log.append("before1")

    @d.before(Animal)
    def before2(x: Animal) -> None:
        log.append("before2")

    @d.before(Animal)
    def before3(x: Animal) -> None:
        log.append("before3")

    d(Animal())
    assert log == ["before1", "before2", "before3"]


# ---------------------------------------------------------------------------
# Multiple after advisors run in reverse registration order
# ---------------------------------------------------------------------------

def test_multiple_after_reverse_order():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        return "primary"

    @d.after(Animal)
    def after1(x: Animal) -> None:
        log.append("after1")

    @d.after(Animal)
    def after2(x: Animal) -> None:
        log.append("after2")

    @d.after(Animal)
    def after3(x: Animal) -> None:
        log.append("after3")

    d(Animal())
    assert log == ["after3", "after2", "after1"]


# ---------------------------------------------------------------------------
# Around advisors nest correctly (outermost first)
# ---------------------------------------------------------------------------

def test_multiple_around_nesting():
    """Outermost :around runs first; innermost wraps closest to primary."""
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        log.append("primary")
        return "done"

    @d.around(Animal)
    def outer(proceed, x: Animal) -> str:
        log.append("outer_enter")
        result = proceed(x)
        log.append("outer_exit")
        return result

    @d.around(Animal)
    def inner(proceed, x: Animal) -> str:
        log.append("inner_enter")
        result = proceed(x)
        log.append("inner_exit")
        return result

    d(Animal())
    assert log == ["outer_enter", "inner_enter", "primary", "inner_exit", "outer_exit"]


# ---------------------------------------------------------------------------
# Traced execution
# ---------------------------------------------------------------------------

def test_call_traced_phases():
    d = Dispatcher("test")

    @d.register
    def handle(x: Animal) -> str:
        return "result"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        pass

    @d.after(Animal)
    def post(x: Animal) -> None:
        pass

    result, trace = d.call_traced(Animal())
    assert result == "result"
    phases = [e.phase for e in trace]
    assert phases == ["before", "primary", "after"]


def test_call_traced_names():
    d = Dispatcher("test")

    @d.register
    def handle_animal(x: Animal) -> str:
        return "result"

    @d.before(Animal)
    def pre_animal(x: Animal) -> None:
        pass

    result, trace = d.call_traced(Animal())
    names = [e.name for e in trace]
    assert "pre_animal" in names[0]
    assert "handle_animal" in names[1]


def test_call_traced_duration_ms_non_negative():
    d = Dispatcher("test")

    @d.register
    def handle(x: Animal) -> str:
        return "r"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        pass

    _, trace = d.call_traced(Animal())
    for entry in trace:
        assert entry.duration_ms >= 0.0


def test_call_traced_type_key():
    d = Dispatcher("test")

    @d.register
    def handle(x: Animal) -> str:
        return "r"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        pass

    @d.after(Animal)
    def post(x: Animal) -> None:
        pass

    _, trace = d.call_traced(Animal())
    before_entry = next(e for e in trace if e.phase == "before")
    after_entry  = next(e for e in trace if e.phase == "after")
    primary_entry = next(e for e in trace if e.phase == "primary")

    assert before_entry.type_key is Animal
    assert after_entry.type_key is Animal
    assert primary_entry.type_key is None


def test_call_traced_around_entry():
    d = Dispatcher("test")

    @d.register
    def handle(x: Animal) -> str:
        return "r"

    @d.around(Animal)
    def wrap(proceed, x: Animal) -> str:
        return proceed(x)

    _, trace = d.call_traced(Animal())
    phases = [e.phase for e in trace]
    assert "around" in phases
    around_entry = next(e for e in trace if e.phase == "around")
    assert around_entry.type_key is Animal


def test_call_traced_no_advisors_primary_only():
    d = Dispatcher("test")

    @d.register
    def handle(x: Animal) -> str:
        return "r"

    result, trace = d.call_traced(Animal())
    assert result == "r"
    assert len(trace) == 1
    assert trace[0].phase == "primary"


# ---------------------------------------------------------------------------
# Async combinations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_before():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    async def handle(x: Animal) -> str:
        log.append("primary")
        return "async_result"

    @d.before(Animal)
    async def pre(x: Animal) -> None:
        await asyncio.sleep(0)
        log.append("async_before")

    result = await d.call_async(Animal())
    assert result == "async_result"
    assert log == ["async_before", "primary"]


@pytest.mark.asyncio
async def test_async_after():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    async def handle(x: Animal) -> str:
        log.append("primary")
        return "result"

    @d.after(Animal)
    async def post(x: Animal) -> None:
        await asyncio.sleep(0)
        log.append("async_after")

    result = await d.call_async(Animal())
    assert result == "result"
    assert log == ["primary", "async_after"]


@pytest.mark.asyncio
async def test_async_around():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    async def handle(x: Animal) -> str:
        log.append("primary")
        return "result"

    @d.around(Animal)
    async def wrap(proceed, x: Animal) -> str:
        log.append("around_enter")
        result = await proceed(x)
        log.append("around_exit")
        return result

    result = await d.call_async(Animal())
    assert result == "result"
    assert log == ["around_enter", "primary", "around_exit"]


@pytest.mark.asyncio
async def test_async_call_async_traced():
    d = Dispatcher("test")

    @d.register
    async def handle(x: Animal) -> str:
        return "r"

    @d.before(Animal)
    async def pre(x: Animal) -> None:
        pass

    @d.after(Animal)
    async def post(x: Animal) -> None:
        pass

    result, trace = await d.call_async_traced(Animal())
    assert result == "r"
    phases = [e.phase for e in trace]
    assert "before" in phases
    assert "primary" in phases
    assert "after" in phases


@pytest.mark.asyncio
async def test_async_mixed_sync_async_advisors():
    """Sync and async advisors can be mixed in the chain."""
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        log.append("primary")
        return "r"

    @d.before(Animal)
    def sync_before(x: Animal) -> None:
        log.append("sync_before")

    @d.before(Animal)
    async def async_before(x: Animal) -> None:
        await asyncio.sleep(0)
        log.append("async_before")

    result = await d.call_async(Animal())
    assert result == "r"
    assert log == ["sync_before", "async_before", "primary"]


# ---------------------------------------------------------------------------
# Interaction with specificity dispatch
# ---------------------------------------------------------------------------

def test_combinations_with_specificity():
    d = Dispatcher("test", specificity=True)
    log: list[str] = []

    @d.register
    def handle_animal(x: Animal) -> str:
        log.append("animal_primary")
        return "animal"

    @d.register
    def handle_dog(x: Dog) -> str:
        log.append("dog_primary")
        return "dog"

    @d.before(Dog)
    def dog_before(x: Dog) -> None:
        log.append("dog_before")

    # Dog-specific handler wins for Dog
    result = d(Dog())
    assert result == "dog"
    assert log == ["dog_before", "dog_primary"]

    log.clear()

    # Animal handler for Cat (no Dog advisor fires)
    result = d(Cat())
    assert result == "animal"
    assert "dog_before" not in log


# ---------------------------------------------------------------------------
# Interaction with priority
# ---------------------------------------------------------------------------

def test_combinations_with_priority():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register(priority=0)
    def low(x: Animal) -> str:
        log.append("low")
        return "low"

    @d.register(priority=10)
    def high(x: Animal) -> str:
        log.append("high")
        return "high"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        log.append("before")

    result = d(Animal())
    # High priority handler wins
    assert result == "high"
    assert log == ["before", "high"]


# ---------------------------------------------------------------------------
# Around can modify arguments to proceed
# ---------------------------------------------------------------------------

def test_around_modifies_arguments():
    d = Dispatcher("test")

    @d.register
    def handle(x: int) -> int:
        return x * 2

    @d.around(int)
    def double_input(proceed, x: int) -> int:
        return proceed(x + 10)

    result = d(5)
    # around passes x+10=15 to primary, primary returns 15*2=30
    assert result == 30


# ---------------------------------------------------------------------------
# Around can modify return value
# ---------------------------------------------------------------------------

def test_around_modifies_return_value():
    d = Dispatcher("test")

    @d.register
    def handle(x: int) -> int:
        return x

    @d.around(int)
    def negate_result(proceed, x: int) -> int:
        return -proceed(x)

    result = d(7)
    assert result == -7


# ---------------------------------------------------------------------------
# No advisors = normal dispatch (backward compatibility)
# ---------------------------------------------------------------------------

def test_no_advisors_backward_compatible():
    d = Dispatcher("test")

    @d.register
    def handle(x: int) -> str:
        return f"int:{x}"

    assert d(42) == "int:42"


def test_no_advisors_multiple_handlers():
    d = Dispatcher("test")

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    @d.register
    def handle_str(x: str) -> str:
        return "str"

    assert d(1) == "int"
    assert d("hi") == "str"


# ---------------------------------------------------------------------------
# Type-specific advisors only fire for matching types
# ---------------------------------------------------------------------------

def test_type_specific_advisors():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle_animal(x: Animal) -> str:
        return "animal"

    @d.before(Dog)
    def dog_only_before(x: Dog) -> None:
        log.append("dog_before")

    # Dog is a subtype of Animal, so Dog-specific advisor fires for Dog
    d(Dog())
    assert "dog_before" in log

    log.clear()

    # Cat does NOT match Dog advisor
    d(Cat())
    assert "dog_before" not in log


def test_subclass_inherits_parent_advisors():
    """Advisors on Animal also fire for Dog (isinstance check)."""
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        return "animal"

    @d.before(Animal)
    def animal_before(x: Animal) -> None:
        log.append("animal_before")

    d(Dog())  # Dog is an Animal
    assert "animal_before" in log


# ---------------------------------------------------------------------------
# Unregister/clear also clears advisors
# ---------------------------------------------------------------------------

def test_unregister_removes_advisor():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        return "r"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        log.append("before")

    d.unregister(pre)
    d(Animal())
    assert log == []


def test_clear_removes_all_advisors():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        return "r"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        log.append("before")

    @d.after(Animal)
    def post(x: Animal) -> None:
        log.append("after")

    @d.around(Animal)
    def wrap(proceed, x: Animal) -> str:
        log.append("around")
        return proceed(x)

    d.clear()
    assert d._before_advisors == []
    assert d._after_advisors == []
    assert d._around_advisors == []


def test_clear_then_fresh_registration():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        return "r"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        log.append("before")

    d.clear()

    # Re-register without advisor
    @d.register
    def handle2(x: Animal) -> str:
        return "r2"

    result = d(Animal())
    assert result == "r2"
    assert log == []


# ---------------------------------------------------------------------------
# CombinationTraceEntry is a NamedTuple with correct fields
# ---------------------------------------------------------------------------

def test_combination_trace_entry_fields():
    entry = CombinationTraceEntry(
        phase="before",
        name="my_func",
        duration_ms=1.5,
        type_key=Animal,
    )
    assert entry.phase == "before"
    assert entry.name == "my_func"
    assert entry.duration_ms == 1.5
    assert entry.type_key is Animal


def test_combination_trace_entry_is_named_tuple():
    entry = CombinationTraceEntry(phase="primary", name="f", duration_ms=0.1, type_key=None)
    # NamedTuple supports indexing
    assert entry[0] == "primary"
    assert entry[1] == "f"


# ---------------------------------------------------------------------------
# Before/after return values are ignored
# ---------------------------------------------------------------------------

def test_before_return_value_ignored():
    d = Dispatcher("test")

    @d.register
    def handle(x: Animal) -> str:
        return "primary_result"

    @d.before(Animal)
    def pre(x: Animal) -> str:
        return "should_be_ignored"

    result = d(Animal())
    assert result == "primary_result"


def test_after_return_value_ignored():
    d = Dispatcher("test")

    @d.register
    def handle(x: Animal) -> str:
        return "primary_result"

    @d.after(Animal)
    def post(x: Animal) -> str:
        return "should_be_ignored"

    result = d(Animal())
    assert result == "primary_result"


# ---------------------------------------------------------------------------
# Fallback handler with combinations
# ---------------------------------------------------------------------------

def test_combinations_with_fallback():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle_int(x: int) -> str:
        return "int"

    @d.fallback
    def catch_all(*args: Any) -> str:
        log.append("fallback")
        return "fallback"

    @d.before(str)
    def pre_str(x: str) -> None:
        log.append("before_str")

    # Falls back, but before_str fires (str is an instance of str)
    result = d("hello")
    assert result == "fallback"
    assert "before_str" in log


# ---------------------------------------------------------------------------
# Around stops the chain when proceed is not called
# ---------------------------------------------------------------------------

def test_around_can_short_circuit():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    def handle(x: Animal) -> str:
        log.append("primary")
        return "primary_result"

    @d.before(Animal)
    def pre(x: Animal) -> None:
        log.append("before")

    @d.around(Animal)
    def short_circuit(proceed, x: Animal) -> str:
        # Deliberately does NOT call proceed
        log.append("around_short_circuit")
        return "short_circuited"

    result = d(Animal())
    assert result == "short_circuited"
    # before and primary should NOT have run
    assert "before" not in log
    assert "primary" not in log
    assert "around_short_circuit" in log


# ---------------------------------------------------------------------------
# Async around nesting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_around_nesting():
    d = Dispatcher("test")
    log: list[str] = []

    @d.register
    async def handle(x: Animal) -> str:
        log.append("primary")
        return "done"

    @d.around(Animal)
    async def outer(proceed, x: Animal) -> str:
        log.append("outer_enter")
        result = await proceed(x)
        log.append("outer_exit")
        return result

    @d.around(Animal)
    async def inner(proceed, x: Animal) -> str:
        log.append("inner_enter")
        result = await proceed(x)
        log.append("inner_exit")
        return result

    result = await d.call_async(Animal())
    assert result == "done"
    assert log == ["outer_enter", "inner_enter", "primary", "inner_exit", "outer_exit"]


# ---------------------------------------------------------------------------
# Export verification
# ---------------------------------------------------------------------------

def test_combination_trace_entry_exported_from_package():
    from live_dispatch import CombinationTraceEntry as CTE
    assert CTE is CombinationTraceEntry
