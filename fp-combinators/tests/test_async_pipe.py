"""Tests for async_pipe."""
from __future__ import annotations

import asyncio
import pytest

from fp_combinators._core import async_pipe
from fp_combinators._result import async_try_pipe, Ok


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def double(x):
    return x * 2


def add_one(x):
    return x + 1


def to_str(x):
    return str(x)


async def async_double(x):
    return x * 2


async def async_add_one(x):
    return x + 1


async def async_to_str(x):
    return str(x)


async def async_upper(s):
    await asyncio.sleep(0)  # yield to event loop
    return s.upper()


# ---------------------------------------------------------------------------
# All synchronous functions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_sync_single():
    result = await async_pipe(5, double)
    assert result == 10


@pytest.mark.asyncio
async def test_all_sync_chain():
    result = await async_pipe(3, add_one, double, to_str)
    assert result == "8"


@pytest.mark.asyncio
async def test_all_sync_identity():
    result = await async_pipe(42, lambda x: x)
    assert result == 42


@pytest.mark.asyncio
async def test_all_sync_string_operations():
    result = await async_pipe("  hello  ", str.strip, str.upper, len)
    assert result == 5


@pytest.mark.asyncio
async def test_all_sync_many_steps():
    # Each step increments by 1
    funcs = [lambda x, i=i: x + 1 for i in range(10)]
    result = await async_pipe(0, *funcs)
    assert result == 10


# ---------------------------------------------------------------------------
# All async functions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_async_single():
    result = await async_pipe(7, async_double)
    assert result == 14


@pytest.mark.asyncio
async def test_all_async_chain():
    result = await async_pipe(3, async_add_one, async_double, async_to_str)
    assert result == "8"


@pytest.mark.asyncio
async def test_all_async_with_sleep():
    result = await async_pipe("world", async_upper)
    assert result == "WORLD"


@pytest.mark.asyncio
async def test_all_async_two_steps():
    result = await async_pipe(10, async_add_one, async_double)
    assert result == 22


# ---------------------------------------------------------------------------
# Mixed sync and async functions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_sync_first_async_second():
    result = await async_pipe(5, double, async_add_one)
    assert result == 11


@pytest.mark.asyncio
async def test_mixed_async_first_sync_second():
    result = await async_pipe(5, async_double, add_one)
    assert result == 11


@pytest.mark.asyncio
async def test_mixed_alternating():
    # sync -> async -> sync -> async
    result = await async_pipe(1, add_one, async_double, add_one, async_double)
    # 1 -> 2 -> 4 -> 5 -> 10
    assert result == 10


@pytest.mark.asyncio
async def test_mixed_string_pipeline():
    result = await async_pipe(
        "  hello  ",
        str.strip,          # sync
        async_upper,        # async (yields to event loop)
        len,                # sync
    )
    assert result == 5


@pytest.mark.asyncio
async def test_mixed_sync_sandwiched_by_async():
    result = await async_pipe(
        2,
        async_double,   # async: 4
        add_one,        # sync: 5
        async_double,   # async: 10
        to_str,         # sync: "10"
    )
    assert result == "10"


# ---------------------------------------------------------------------------
# Empty function list — returns value unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_funcs_returns_value_int():
    result = await async_pipe(99)
    assert result == 99


@pytest.mark.asyncio
async def test_empty_funcs_returns_value_string():
    result = await async_pipe("hello")
    assert result == "hello"


@pytest.mark.asyncio
async def test_empty_funcs_returns_none():
    result = await async_pipe(None)
    assert result is None


@pytest.mark.asyncio
async def test_empty_funcs_returns_list():
    lst = [1, 2, 3]
    result = await async_pipe(lst)
    assert result is lst


# ---------------------------------------------------------------------------
# Coroutine detection — ensure sync return values are NOT awaited
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_function_returning_int_not_awaited():
    """Sync functions returning plain ints must not be treated as coroutines."""
    result = await async_pipe(5, lambda x: x + 1)
    assert result == 6


@pytest.mark.asyncio
async def test_coroutines_are_awaited_exactly_once():
    """Each async function must be awaited exactly once."""
    call_count = 0

    async def counting_async(x):
        nonlocal call_count
        call_count += 1
        return x

    await async_pipe(0, counting_async, counting_async, counting_async)
    assert call_count == 3


@pytest.mark.asyncio
async def test_async_pipe_propagates_exceptions():
    """Exceptions from async functions bubble up normally."""
    async def boom(x):
        raise ValueError("async explode")

    with pytest.raises(ValueError, match="async explode"):
        await async_pipe(1, boom)


@pytest.mark.asyncio
async def test_sync_pipe_propagates_exceptions():
    """Exceptions from sync functions bubble up normally."""
    def boom(x):
        raise RuntimeError("sync explode")

    with pytest.raises(RuntimeError, match="sync explode"):
        await async_pipe(1, boom)


# ---------------------------------------------------------------------------
# async_try_pipe tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_try_pipe_all_sync_success():
    result = await async_try_pipe("42", int, double)
    assert result == Ok(84)


@pytest.mark.asyncio
async def test_async_try_pipe_all_sync_error():
    result = await async_try_pipe("not_a_number", int)
    assert result.is_err()


@pytest.mark.asyncio
async def test_async_try_pipe_async_success():
    result = await async_try_pipe(5, async_double, add_one)
    assert result == Ok(11)


@pytest.mark.asyncio
async def test_async_try_pipe_async_error():
    async def boom(x):
        raise ValueError("async boom")

    result = await async_try_pipe(1, boom)
    assert result.is_err()
    assert "async boom" in str(result.unwrap_err())


class _CustomAwaitable:
    def __init__(self, value):
        self._value = value

    def __await__(self):
        async def _inner():
            return self._value
        return _inner().__await__()


@pytest.mark.asyncio
async def test_async_pipe_awaits_future_results():
    loop = asyncio.get_running_loop()

    def make_future(x):
        fut = loop.create_future()
        fut.set_result(x + 2)
        return fut

    result = await async_pipe(5, make_future, double)
    assert result == 14


@pytest.mark.asyncio
async def test_async_pipe_awaits_custom_awaitables():
    result = await async_pipe(3, lambda x: _CustomAwaitable(x + 4), double)
    assert result == 14


@pytest.mark.asyncio
async def test_async_try_pipe_awaits_task_results():
    async def plus_three(x):
        return x + 3

    def make_task(x):
        return asyncio.create_task(plus_three(x))

    result = await async_try_pipe(4, make_task, double)
    assert result == Ok(14)


@pytest.mark.asyncio
async def test_async_try_pipe_catches_custom_awaitable_errors():
    class _BoomAwaitable:
        def __await__(self):
            async def _inner():
                raise RuntimeError("awaitable boom")
            return _inner().__await__()

    result = await async_try_pipe(1, lambda _: _BoomAwaitable())
    assert result.is_err()
    assert "awaitable boom" in str(result.unwrap_err())


@pytest.mark.asyncio
async def test_async_try_pipe_mixed_sync_async():
    result = await async_try_pipe(3, add_one, async_double, to_str)
    assert result == Ok("8")


@pytest.mark.asyncio
async def test_async_try_pipe_error_midway():
    def fail_on_ten(x):
        if x == 10:
            raise RuntimeError("ten is bad")
        return x

    result = await async_try_pipe(5, async_double, fail_on_ten)
    assert result.is_err()


@pytest.mark.asyncio
async def test_async_try_pipe_empty():
    result = await async_try_pipe(42)
    assert result == Ok(42)
