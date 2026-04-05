"""Tests for newly added Result APIs:
- Result.from_awaitable
- Result.from_call
- Result.async_map
- Result.async_and_then
- sequence()
- traverse()
"""
from __future__ import annotations

import asyncio

import pytest

from fp_combinators import Err, Ok, Result, sequence, traverse


# ---------------------------------------------------------------------------
# Result.from_call
# ---------------------------------------------------------------------------

class TestFromCall:
    def test_from_call_success_wraps_in_ok(self):
        result = Result.from_call(int, "42")
        assert result == Ok(42)

    def test_from_call_exception_wraps_in_err(self):
        result = Result.from_call(int, "not-a-number")
        assert result.is_err()
        assert isinstance(result.unwrap_err(), ValueError)

    def test_from_call_with_kwargs(self):
        def greet(name: str, *, upper: bool = False) -> str:
            if upper:
                return name.upper()
            return name

        assert Result.from_call(greet, "alice", upper=True) == Ok("ALICE")
        assert Result.from_call(greet, "alice") == Ok("alice")

    def test_from_call_no_args(self):
        result = Result.from_call(lambda: 99)
        assert result == Ok(99)

    def test_from_call_captures_runtime_error(self):
        def boom() -> int:
            raise RuntimeError("kaboom")

        result = Result.from_call(boom)
        assert result.is_err()
        assert isinstance(result.unwrap_err(), RuntimeError)
        assert "kaboom" in str(result.unwrap_err())

    def test_from_call_ok_type_is_ok_instance(self):
        result = Result.from_call(str, 42)
        assert isinstance(result, Ok)

    def test_from_call_err_type_is_err_instance(self):
        result = Result.from_call(int, "bad")
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Result.from_awaitable
# ---------------------------------------------------------------------------

class TestFromAwaitable:
    @pytest.mark.asyncio
    async def test_from_awaitable_success(self):
        async def fetch() -> int:
            return 7

        result = await Result.from_awaitable(fetch())
        assert result == Ok(7)

    @pytest.mark.asyncio
    async def test_from_awaitable_exception_becomes_err(self):
        async def fail() -> int:
            raise ValueError("async failure")

        result = await Result.from_awaitable(fail())
        assert result.is_err()
        assert isinstance(result.unwrap_err(), ValueError)
        assert "async failure" in str(result.unwrap_err())

    @pytest.mark.asyncio
    async def test_from_awaitable_with_coroutine_object(self):
        async def compute(x: int) -> int:
            return x * 2

        result = await Result.from_awaitable(compute(21))
        assert result == Ok(42)

    @pytest.mark.asyncio
    async def test_from_awaitable_wraps_none(self):
        async def returns_none() -> None:
            return None

        result = await Result.from_awaitable(returns_none())
        assert result == Ok(None)

    @pytest.mark.asyncio
    async def test_from_awaitable_future_success(self):
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[str] = loop.create_future()
        fut.set_result("done")
        result = await Result.from_awaitable(fut)
        assert result == Ok("done")

    @pytest.mark.asyncio
    async def test_from_awaitable_future_exception(self):
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[str] = loop.create_future()
        fut.set_exception(RuntimeError("future failed"))
        result = await Result.from_awaitable(fut)
        assert result.is_err()
        assert isinstance(result.unwrap_err(), RuntimeError)


# ---------------------------------------------------------------------------
# Result.async_map
# ---------------------------------------------------------------------------

class TestAsyncMap:
    @pytest.mark.asyncio
    async def test_async_map_ok_transforms_value(self):
        async def double(x: int) -> int:
            return x * 2

        result = await Ok(5).async_map(double)
        assert result == Ok(10)

    @pytest.mark.asyncio
    async def test_async_map_err_passes_through(self):
        async def double(x: int) -> int:
            return x * 2

        err: Result[int, str] = Err("bad")
        result = await err.async_map(double)
        assert result is err

    @pytest.mark.asyncio
    async def test_async_map_not_called_on_err(self):
        called = []

        async def side_effect(x: int) -> int:
            called.append(x)
            return x

        await Err("nope").async_map(side_effect)
        assert called == []

    @pytest.mark.asyncio
    async def test_async_map_type_change(self):
        async def to_str(x: int) -> str:
            return str(x)

        result = await Ok(42).async_map(to_str)
        assert result == Ok("42")

    @pytest.mark.asyncio
    async def test_async_map_chaining(self):
        async def add_one(x: int) -> int:
            return x + 1

        async def times_ten(x: int) -> int:
            return x * 10

        result = await Ok(2).async_map(add_one)
        result = await result.async_map(times_ten)
        assert result == Ok(30)


# ---------------------------------------------------------------------------
# Result.async_and_then
# ---------------------------------------------------------------------------

class TestAsyncAndThen:
    @pytest.mark.asyncio
    async def test_async_and_then_ok_to_ok(self):
        async def safe_inc(x: int) -> Result[int, str]:
            return Ok(x + 1)

        result = await Ok(5).async_and_then(safe_inc)
        assert result == Ok(6)

    @pytest.mark.asyncio
    async def test_async_and_then_ok_to_err(self):
        async def reject_negative(x: int) -> Result[int, str]:
            if x < 0:
                return Err("negative")
            return Ok(x)

        result = await Ok(-3).async_and_then(reject_negative)
        assert result == Err("negative")

    @pytest.mark.asyncio
    async def test_async_and_then_err_short_circuits(self):
        called = []

        async def side_effect(x: int) -> Result[int, str]:
            called.append(x)
            return Ok(x)

        err: Result[int, str] = Err("already failed")
        result = await err.async_and_then(side_effect)
        assert result is err
        assert called == []

    @pytest.mark.asyncio
    async def test_async_and_then_chaining(self):
        async def step_a(x: int) -> Result[int, str]:
            return Ok(x * 2) if x > 0 else Err("non-positive")

        async def step_b(x: int) -> Result[str, str]:
            return Ok(f"value={x}")

        result = await Ok(3).async_and_then(step_a)
        result2 = await result.async_and_then(step_b)
        assert result2 == Ok("value=6")

    @pytest.mark.asyncio
    async def test_async_and_then_err_propagates_through_chain(self):
        async def step(x: int) -> Result[int, str]:
            return Ok(x + 1)

        err: Result[int, str] = Err("original")
        r1 = await err.async_and_then(step)
        r2 = await r1.async_and_then(step)
        assert r2 == Err("original")


# ---------------------------------------------------------------------------
# sequence()
# ---------------------------------------------------------------------------

class TestSequence:
    def test_all_ok_returns_ok_list(self):
        result = sequence([Ok(1), Ok(2), Ok(3)])
        assert result == Ok([1, 2, 3])

    def test_empty_iterable_returns_ok_empty_list(self):
        result = sequence([])
        assert result == Ok([])

    def test_first_err_short_circuits(self):
        called = []

        def make_ok(x: int) -> Result[int, str]:
            called.append(x)
            return Ok(x)

        results = [Ok(1), Err("oops"), Ok(3)]
        result = sequence(results)
        assert result == Err("oops")

    def test_err_among_oks_returns_first_err(self):
        results: list[Result[int, str]] = [Ok(1), Err("first"), Err("second")]
        result = sequence(results)
        assert result == Err("first")

    def test_single_ok(self):
        assert sequence([Ok(42)]) == Ok([42])

    def test_single_err(self):
        assert sequence([Err("bad")]) == Err("bad")

    def test_preserves_order(self):
        result = sequence([Ok(10), Ok(20), Ok(30)])
        assert result.unwrap() == [10, 20, 30]

    def test_generator_input(self):
        # sequence should accept any Iterable
        result = sequence(Ok(i) for i in range(4))
        assert result == Ok([0, 1, 2, 3])

    def test_err_from_generator_short_circuits(self):
        def gen() -> Result[int, str]:  # type: ignore[misc]
            # yields Ok(0), Err('stop'), Ok(2) — but third should never be seen
            yield Ok(0)  # type: ignore[misc]
            yield Err("stop")  # type: ignore[misc]
            yield Ok(2)  # type: ignore[misc]

        result = sequence(gen())
        assert result == Err("stop")


# ---------------------------------------------------------------------------
# traverse()
# ---------------------------------------------------------------------------

class TestTraverse:
    def test_all_success_returns_ok_list(self):
        result = traverse([1, 2, 3], lambda x: Ok(x * 2))
        assert result == Ok([2, 4, 6])

    def test_empty_iterable_returns_ok_empty_list(self):
        result = traverse([], lambda x: Ok(x))
        assert result == Ok([])

    def test_first_err_short_circuits(self):
        called: list[int] = []

        def func(x: int) -> Result[int, str]:
            called.append(x)
            if x == 2:
                return Err("two is bad")
            return Ok(x)

        result = traverse([1, 2, 3], func)
        assert result == Err("two is bad")
        # 3 should NOT have been processed
        assert called == [1, 2]

    def test_preserves_order(self):
        result = traverse([3, 1, 4], lambda x: Ok(x + 10))
        assert result == Ok([13, 11, 14])

    def test_returns_first_err_not_last(self):
        def func(x: int) -> Result[int, str]:
            if x < 0:
                return Err(f"negative: {x}")
            return Ok(x)

        result = traverse([1, -2, -3, 4], func)
        assert result == Err("negative: -2")

    def test_generator_input(self):
        result = traverse((x for x in range(1, 4)), lambda x: Ok(x ** 2))
        assert result == Ok([1, 4, 9])

    def test_func_receives_original_items(self):
        seen: list[str] = []

        def func(s: str) -> Result[str, str]:
            seen.append(s)
            return Ok(s.upper())

        traverse(["a", "b", "c"], func)
        assert seen == ["a", "b", "c"]

    def test_type_change_via_func(self):
        result = traverse([1, 2, 3], lambda x: Ok(str(x)))
        assert result == Ok(["1", "2", "3"])


# ---------------------------------------------------------------------------
# Public API exports
# ---------------------------------------------------------------------------

class TestPublicAPIExports:
    def test_sequence_exported_from_package(self):
        from fp_combinators import sequence as seq  # noqa: F401
        assert callable(seq)

    def test_traverse_exported_from_package(self):
        from fp_combinators import traverse as trav  # noqa: F401
        assert callable(trav)

    def test_result_from_call_accessible(self):
        assert callable(Result.from_call)

    @pytest.mark.asyncio
    async def test_result_from_awaitable_accessible(self):
        async def noop() -> int:
            return 0

        r = await Result.from_awaitable(noop())
        assert r == Ok(0)
