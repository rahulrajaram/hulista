"""CLOS-inspired method combinations for live-dispatch.

Provides before/after/around advisor support for the Dispatcher class.

Execution semantics:
1. :around advisors are called outermost-first; each receives a `proceed`
   callable as its first argument.  Calling proceed() invokes the next
   :around or — once all :around advisors have been entered — the
   before+primary+after chain.
2. :before advisors run in registration order before the primary method.
   Return values are ignored.
3. The primary handler runs and its return value is the final result (unless
   an :around advisor intercepts it).
4. :after advisors run in reverse registration order after the primary method.
   Return values are ignored.
"""
from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class CombinationTraceEntry(NamedTuple):
    """A single entry in the method-combination execution trace."""

    phase: Literal["before", "around", "primary", "after"]
    name: str
    duration_ms: float
    type_key: type[Any] | None


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

@dataclass
class _Advisor:
    """A registered advisor (before/after/around) for a specific type."""

    func: Callable[..., Any]
    phase: Literal["before", "after", "around"]
    type_key: type[Any]
    is_async: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_async = inspect.iscoroutinefunction(self.func)


# ---------------------------------------------------------------------------
# Combination execution helpers
# ---------------------------------------------------------------------------

def _run_combination_chain(
    *,
    primary_func: Callable[..., Any],
    before_advisors: list[_Advisor],
    after_advisors: list[_Advisor],
    around_advisors: list[_Advisor],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    trace: list[CombinationTraceEntry] | None,
) -> Any:
    """Execute the synchronous method-combination chain and return the result.

    If *trace* is a list, it is populated with timing entries.
    """

    def run_primary_with_before_after() -> Any:
        # Before advisors — registration order, return values ignored.
        for adv in before_advisors:
            t0 = time.perf_counter()
            adv.func(*args, **kwargs)
            duration = (time.perf_counter() - t0) * 1000.0
            if trace is not None:
                trace.append(CombinationTraceEntry(
                    phase="before",
                    name=adv.func.__qualname__,
                    duration_ms=duration,
                    type_key=adv.type_key,
                ))

        # Primary handler.
        t0 = time.perf_counter()
        result = primary_func(*args, **kwargs)
        duration = (time.perf_counter() - t0) * 1000.0
        if trace is not None:
            trace.append(CombinationTraceEntry(
                phase="primary",
                name=primary_func.__qualname__,
                duration_ms=duration,
                type_key=None,
            ))

        # After advisors — reverse registration order, return values ignored.
        for adv in reversed(after_advisors):
            t0 = time.perf_counter()
            adv.func(*args, **kwargs)
            duration = (time.perf_counter() - t0) * 1000.0
            if trace is not None:
                trace.append(CombinationTraceEntry(
                    phase="after",
                    name=adv.func.__qualname__,
                    duration_ms=duration,
                    type_key=adv.type_key,
                ))

        return result

    if not around_advisors:
        return run_primary_with_before_after()

    # Build a nested proceed chain from inside out.
    # around_advisors[0] is the outermost, so we build the chain starting
    # from the innermost (run_primary_with_before_after).

    def make_proceed(index: int) -> Callable[..., Any]:
        if index >= len(around_advisors):
            # Innermost proceed: run before+primary+after
            def innermost_proceed(*a: Any, **kw: Any) -> Any:
                nonlocal args, kwargs
                args = a
                kwargs = kw
                return run_primary_with_before_after()
            return innermost_proceed

        adv = around_advisors[index]
        next_proceed = make_proceed(index + 1)

        def this_proceed(*a: Any, **kw: Any) -> Any:
            nonlocal args, kwargs
            args = a
            kwargs = kw
            t0 = time.perf_counter()
            res = adv.func(next_proceed, *a, **kw)
            duration = (time.perf_counter() - t0) * 1000.0
            if trace is not None:
                trace.append(CombinationTraceEntry(
                    phase="around",
                    name=adv.func.__qualname__,
                    duration_ms=duration,
                    type_key=adv.type_key,
                ))
            return res

        return this_proceed

    outermost_proceed = make_proceed(0)
    return outermost_proceed(*args, **kwargs)


async def _run_combination_chain_async(
    *,
    primary_func: Callable[..., Any],
    before_advisors: list[_Advisor],
    after_advisors: list[_Advisor],
    around_advisors: list[_Advisor],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    trace: list[CombinationTraceEntry] | None,
) -> Any:
    """Execute the async method-combination chain and return the result.

    Awaits any advisor or handler that returns a coroutine/awaitable.
    If *trace* is a list, it is populated with timing entries.
    """

    async def run_primary_with_before_after() -> Any:
        # Before advisors.
        for adv in before_advisors:
            t0 = time.perf_counter()
            ret = adv.func(*args, **kwargs)
            if inspect.isawaitable(ret):
                await ret
            duration = (time.perf_counter() - t0) * 1000.0
            if trace is not None:
                trace.append(CombinationTraceEntry(
                    phase="before",
                    name=adv.func.__qualname__,
                    duration_ms=duration,
                    type_key=adv.type_key,
                ))

        # Primary handler.
        t0 = time.perf_counter()
        ret = primary_func(*args, **kwargs)
        if inspect.isawaitable(ret):
            result = await ret
        else:
            result = ret
        duration = (time.perf_counter() - t0) * 1000.0
        if trace is not None:
            trace.append(CombinationTraceEntry(
                phase="primary",
                name=primary_func.__qualname__,
                duration_ms=duration,
                type_key=None,
            ))

        # After advisors (reverse order).
        for adv in reversed(after_advisors):
            t0 = time.perf_counter()
            ret = adv.func(*args, **kwargs)
            if inspect.isawaitable(ret):
                await ret
            duration = (time.perf_counter() - t0) * 1000.0
            if trace is not None:
                trace.append(CombinationTraceEntry(
                    phase="after",
                    name=adv.func.__qualname__,
                    duration_ms=duration,
                    type_key=adv.type_key,
                ))

        return result

    if not around_advisors:
        return await run_primary_with_before_after()

    # Build async nested proceed chain.
    def make_async_proceed(index: int) -> Callable[..., Any]:
        if index >= len(around_advisors):
            async def innermost_proceed(*a: Any, **kw: Any) -> Any:
                nonlocal args, kwargs
                args = a
                kwargs = kw
                return await run_primary_with_before_after()
            return innermost_proceed

        adv = around_advisors[index]
        next_proceed = make_async_proceed(index + 1)

        async def this_proceed(*a: Any, **kw: Any) -> Any:
            nonlocal args, kwargs
            args = a
            kwargs = kw
            t0 = time.perf_counter()
            ret = adv.func(next_proceed, *a, **kw)
            if inspect.isawaitable(ret):
                res = await ret
            else:
                res = ret
            duration = (time.perf_counter() - t0) * 1000.0
            if trace is not None:
                trace.append(CombinationTraceEntry(
                    phase="around",
                    name=adv.func.__qualname__,
                    duration_ms=duration,
                    type_key=adv.type_key,
                ))
            return res

        return this_proceed

    outermost_proceed = make_async_proceed(0)
    return await outermost_proceed(*args, **kwargs)
