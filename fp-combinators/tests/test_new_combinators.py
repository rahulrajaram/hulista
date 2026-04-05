"""Tests for resilient_pipe, traced_pipe, when, and traverse_all."""
from __future__ import annotations

import asyncio

import pytest

from fp_combinators import (
    Err,
    Ok,
    Result,
    async_resilient_pipe,
    async_traced_pipe,
    resilient_pipe,
    traced_pipe,
    traverse_all,
    when,
)


def test_when_applies_stage_when_predicate_matches():
    stage = when(lambda x: x > 0, lambda x: x * 2)
    assert stage(3) == 6


def test_when_returns_original_value_when_predicate_fails():
    stage = when(lambda x: x > 0, lambda x: x * 2)
    value = -4
    assert stage(value) == value


def test_resilient_pipe_continues_after_exception_with_last_good_value():
    result = resilient_pipe(
        3,
        lambda x: x + 1,
        lambda x: (_ for _ in ()).throw(ValueError("boom")),
        lambda x: x * 10,
    )
    assert result == 40


def test_resilient_pipe_on_error_receives_stage_exception_and_value():
    calls: list[tuple[str, str, int]] = []

    def fail(value: int) -> int:
        raise RuntimeError("nope")

    def on_error(stage, exc: Exception, value: int) -> int:
        calls.append((stage.__name__, str(exc), value))
        return value + 5

    result = resilient_pipe(10, fail, lambda x: x * 2, on_error=on_error)
    assert result == 30
    assert calls == [("fail", "nope", 10)]


def test_traced_pipe_records_stage_names_change_flags_and_durations():
    result, trace = traced_pipe(
        "  hello  ",
        str.strip,
        lambda s: s,
        str.upper,
    )
    assert result == "HELLO"
    assert [entry.name for entry in trace] == ["strip", "<lambda>", "upper"]
    assert [entry.changed for entry in trace] == [True, False, True]
    assert all(entry.duration_ms >= 0 for entry in trace)


def test_traced_pipe_with_no_stages_returns_empty_trace():
    value = {"x": 1}
    result, trace = traced_pipe(value)
    assert result is value
    assert trace == []


@pytest.mark.asyncio
async def test_async_resilient_pipe_supports_mixed_sync_async_stages_and_callback():
    async def async_fail(value: int) -> int:
        raise ValueError("async boom")

    async def on_error(stage, exc: Exception, value: int) -> int:
        await asyncio.sleep(0)
        return value + 4

    result = await async_resilient_pipe(
        2,
        lambda x: x + 1,
        async_fail,
        lambda x: x * 3,
        on_error=on_error,
    )
    assert result == 21


@pytest.mark.asyncio
async def test_async_traced_pipe_records_async_stage_transitions():
    async def async_upper(value: str) -> str:
        await asyncio.sleep(0)
        return value.upper()

    result, trace = await async_traced_pipe("hi", async_upper, lambda s: f"{s}!")
    assert result == "HI!"
    assert [entry.name for entry in trace] == ["async_upper", "<lambda>"]
    assert [entry.changed for entry in trace] == [True, True]
    assert all(entry.duration_ms >= 0 for entry in trace)


def test_traverse_all_collects_every_error_and_processes_all_items():
    seen: list[int] = []

    def validate(value: int) -> Result[int, str]:
        seen.append(value)
        if value % 2:
            return Err(f"odd:{value}")
        return Ok(value * 10)

    result = traverse_all([1, 2, 3, 4], validate)
    assert result == Err(["odd:1", "odd:3"])
    assert seen == [1, 2, 3, 4]


def test_traverse_all_returns_ok_when_every_item_succeeds():
    result = traverse_all([1, 2, 3], lambda value: Ok(value + 1))
    assert result == Ok([2, 3, 4])
