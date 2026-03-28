"""Public API smoke tests for fp_combinators."""
from __future__ import annotations

import pytest

from fp_combinators import Err, Ok, Result, async_pipe, async_try_pipe, pipe, try_pipe


def test_public_imports_expose_exported_symbols():
    assert pipe(2, lambda x: x + 1) == 3
    assert try_pipe("42", int) == Ok(42)
    assert isinstance(Err("boom"), Result)


@pytest.mark.asyncio
async def test_public_async_exports_work():
    result = await async_pipe(3, lambda x: x + 1)
    assert result == 4

    try_result = await async_try_pipe("5", int)
    assert try_result == Ok(5)
