"""Public API smoke tests for fp_combinators."""
from __future__ import annotations

import pytest

from fp_combinators import (
    Err,
    Ok,
    Result,
    TraceEntry,
    async_pipe,
    async_resilient_pipe,
    async_traced_pipe,
    async_try_pipe,
    pipe,
    resilient_pipe,
    traced_pipe,
    traverse_all,
    try_pipe,
    when,
)


def test_public_imports_expose_exported_symbols():
    assert pipe(2, lambda x: x + 1) == 3
    assert try_pipe("42", int) == Ok(42)
    assert isinstance(Err("boom"), Result)
    assert resilient_pipe(2, lambda x: x + 1) == 3
    assert when(lambda x: x > 0, lambda x: x * 2)(4) == 8
    traced_value, traced = traced_pipe(2, lambda x: x + 1)
    assert traced_value == 3
    assert isinstance(traced[0], TraceEntry)
    assert traverse_all([1, 2], lambda x: Ok(x)) == Ok([1, 2])


@pytest.mark.asyncio
async def test_public_async_exports_work():
    result = await async_pipe(3, lambda x: x + 1)
    assert result == 4

    try_result = await async_try_pipe("5", int)
    assert try_result == Ok(5)

    resilient = await async_resilient_pipe(3, lambda x: x + 1)
    assert resilient == 4

    traced_value, traced = await async_traced_pipe(3, lambda x: x + 1)
    assert traced_value == 4
    assert isinstance(traced[0], TraceEntry)
