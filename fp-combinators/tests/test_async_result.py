"""Tests for async_sequence, async_traverse, and async_traverse_all."""
from __future__ import annotations

import asyncio

import pytest

from fp_combinators._result import (
    Err,
    Ok,
    async_sequence,
    async_traverse,
    async_traverse_all,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def ok_after(value, *, delay: float = 0.0):
    """Return Ok(value) after an optional delay."""
    if delay:
        await asyncio.sleep(delay)
    return Ok(value)


async def err_after(error, *, delay: float = 0.0):
    """Return Err(error) after an optional delay."""
    if delay:
        await asyncio.sleep(delay)
    return Err(error)


# ---------------------------------------------------------------------------
# TestAsyncSequence
# ---------------------------------------------------------------------------

class TestAsyncSequence:
    @pytest.mark.asyncio
    async def test_all_ok_returns_ok_list(self):
        awaitables = [ok_after(1), ok_after(2), ok_after(3)]
        result = await async_sequence(awaitables)
        assert result == Ok([1, 2, 3])

    @pytest.mark.asyncio
    async def test_empty_returns_ok_empty_list(self):
        result = await async_sequence([])
        assert result == Ok([])

    @pytest.mark.asyncio
    async def test_first_err_short_circuits(self):
        """Items after the first Err must NOT be awaited."""
        awaited = []

        async def tracked(value, *, should_fail: bool = False):
            awaited.append(value)
            return Err(f"fail:{value}") if should_fail else Ok(value)

        awaitables = [
            tracked(1),
            tracked(2, should_fail=True),
            tracked(3),   # must not be awaited
        ]
        result = await async_sequence(awaitables)
        assert result == Err("fail:2")
        assert awaited == [1, 2], "item 3 should not have been awaited"

    @pytest.mark.asyncio
    async def test_err_among_oks_returns_first_err(self):
        awaitables = [ok_after(10), err_after("boom"), ok_after(30)]
        result = await async_sequence(awaitables)
        assert result == Err("boom")

    @pytest.mark.asyncio
    async def test_preserves_order(self):
        awaitables = [ok_after(100), ok_after(1), ok_after(50)]
        result = await async_sequence(awaitables)
        assert result == Ok([100, 1, 50])


# ---------------------------------------------------------------------------
# TestAsyncTraverse
# ---------------------------------------------------------------------------

class TestAsyncTraverse:
    @pytest.mark.asyncio
    async def test_all_success_returns_ok_list(self):
        async def double(x: int):
            return Ok(x * 2)

        result = await async_traverse([1, 2, 3], double)
        assert result == Ok([2, 4, 6])

    @pytest.mark.asyncio
    async def test_empty_returns_ok_empty_list(self):
        async def double(x: int):
            return Ok(x * 2)

        result = await async_traverse([], double)
        assert result == Ok([])

    @pytest.mark.asyncio
    async def test_first_err_short_circuits(self):
        """Items after the first Err must NOT be processed."""
        processed = []

        async def checked(x: int):
            processed.append(x)
            return Err(f"bad:{x}") if x < 0 else Ok(x)

        result = await async_traverse([1, -1, 3], checked)
        assert result == Err("bad:-1")
        assert processed == [1, -1], "item 3 should not have been processed"

    @pytest.mark.asyncio
    async def test_preserves_order(self):
        async def identity(x: int):
            return Ok(x)

        result = await async_traverse([5, 3, 9, 1], identity)
        assert result == Ok([5, 3, 9, 1])

    @pytest.mark.asyncio
    async def test_type_change_via_func(self):
        async def to_str(x: int):
            return Ok(str(x))

        result = await async_traverse([1, 2, 3], to_str)
        assert result == Ok(["1", "2", "3"])

    @pytest.mark.asyncio
    async def test_func_receives_original_items(self):
        received = []

        async def record(x: int):
            received.append(x)
            return Ok(x)

        items = [10, 20, 30]
        await async_traverse(items, record)
        assert received == items


# ---------------------------------------------------------------------------
# TestAsyncTraverseAll
# ---------------------------------------------------------------------------

class TestAsyncTraverseAll:
    @pytest.mark.asyncio
    async def test_all_success_returns_ok_list(self):
        async def double(x: int):
            return Ok(x * 2)

        result = await async_traverse_all([1, 2, 3], double)
        assert result == Ok([2, 4, 6])

    @pytest.mark.asyncio
    async def test_collects_all_errors(self):
        async def checked(x: int):
            return Err(f"bad:{x}") if x < 0 else Ok(x)

        result = await async_traverse_all([1, -1, 3, -2], checked)
        assert result == Err(["bad:-1", "bad:-2"])

    @pytest.mark.asyncio
    async def test_empty_returns_ok_empty_list(self):
        async def identity(x: int):
            return Ok(x)

        result = await async_traverse_all([], identity)
        assert result == Ok([])

    @pytest.mark.asyncio
    async def test_preserves_ok_order(self):
        async def identity(x: int):
            return Ok(x)

        result = await async_traverse_all([7, 2, 5], identity)
        assert result == Ok([7, 2, 5])

    @pytest.mark.asyncio
    async def test_processes_all_items_even_after_errors(self):
        """All items must be processed regardless of intermediate errors."""
        processed = []

        async def checked(x: int):
            processed.append(x)
            return Err(f"bad:{x}") if x < 0 else Ok(x)

        items = [1, -1, 3, -2, 5]
        result = await async_traverse_all(items, checked)
        assert result.is_err()
        assert processed == items, "every item must have been processed"
        assert result == Err(["bad:-1", "bad:-2"])


# ---------------------------------------------------------------------------
# TestSequentialBehavior
# ---------------------------------------------------------------------------

class TestSequentialBehavior:
    @pytest.mark.asyncio
    async def test_async_traverse_executes_sequentially(self):
        """Prove that items are processed one at a time, not concurrently.

        If processing were parallel, item 3 could complete before item 2.
        With sequential execution the finish order must match the input order.
        """
        order: list[str] = []

        async def timed_step(label: str, delay: float):
            order.append(f"start:{label}")
            await asyncio.sleep(delay)
            order.append(f"end:{label}")
            return Ok(label)

        # Items with different delays: if run concurrently, "b" (0.01s) would
        # finish before "a" (0.05s). Sequentially, "a" always finishes first.
        items = [("a", 0.05), ("b", 0.01), ("c", 0.02)]

        async def run(item):
            label, delay = item
            return await timed_step(label, delay)

        result = await async_traverse(items, run)
        assert result.is_ok()

        # Sequential: each item starts only after the previous one ends.
        assert order == [
            "start:a", "end:a",
            "start:b", "end:b",
            "start:c", "end:c",
        ]
