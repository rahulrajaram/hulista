"""Lightweight FP combinators for Python."""
from __future__ import annotations

import inspect
from collections import namedtuple
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any, TypeVar

T = TypeVar('T')

TraceEntry = namedtuple('TraceEntry', ['name', 'changed', 'duration_ms'])


def _callable_name(func: Callable) -> str:
    return getattr(func, '__name__', getattr(func, '__qualname__', repr(func)))


def _value_changed(before: Any, after: Any) -> bool:
    if after is before:
        return False
    try:
        return bool(after != before)
    except Exception:
        return True


def pipe(value: Any, /, *funcs: Callable) -> Any:
    """Thread a value through functions left-to-right.

    pipe(x, f, g, h) == h(g(f(x)))
    """
    for f in funcs:
        value = f(value)
    return value


def compose(*funcs: Callable) -> Callable:
    """Compose functions right-to-left into a single callable.

    compose(f, g, h)(x) == f(g(h(x)))
    """
    if not funcs:
        raise TypeError("compose requires at least one function")
    if len(funcs) == 1:
        return funcs[0]

    def _composed(*args: Any, **kwargs: Any) -> Any:
        result = funcs[-1](*args, **kwargs)
        for f in reversed(funcs[:-1]):
            result = f(result)
        return result

    _composed.__qualname__ = ' \u2218 '.join(
        getattr(f, '__qualname__', repr(f)) for f in funcs
    )
    return _composed


def first_some(*funcs: Callable[..., T | None]) -> Callable[..., T | None]:
    """Return a function that calls each func, returning the first non-None result.

    Short-circuits on first non-None return value.
    """
    if not funcs:
        raise TypeError("first_some requires at least one function")

    def _first(*args: Any, **kwargs: Any) -> T | None:
        for f in funcs:
            result = f(*args, **kwargs)
            if result is not None:
                return result
        return None

    _first.__qualname__ = 'first_some(' + ', '.join(
        getattr(f, '__qualname__', repr(f)) for f in funcs
    ) + ')'
    return _first


def pipeline(*funcs: Callable) -> Callable:
    """Create a left-to-right pipeline callable.

    Unlike compose (right-to-left), pipeline reads in execution order.
    pipeline(f, g, h)(x) == h(g(f(x)))
    """
    if not funcs:
        raise TypeError("pipeline requires at least one function")
    if len(funcs) == 1:
        return funcs[0]

    def _pipeline(*args: Any, **kwargs: Any) -> Any:
        result = funcs[0](*args, **kwargs)
        for f in funcs[1:]:
            result = f(result)
        return result

    _pipeline.__qualname__ = ' | '.join(
        getattr(f, '__qualname__', repr(f)) for f in funcs
    )
    return _pipeline


async def async_pipe(value: Any, /, *funcs: Callable) -> Any:
    """Thread a value through functions left-to-right, awaiting coroutines.

    Like pipe(), but transparently handles both sync and async functions.
    If a function returns a coroutine, it is awaited before passing to the next.

    async_pipe(x, sync_fn, async_fn, sync_fn) works seamlessly.
    """
    for f in funcs:
        result = f(value)
        if inspect.isawaitable(result):
            value = await result
        else:
            value = result
    return value


def resilient_pipe(
    value: Any,
    /,
    *funcs: Callable,
    on_error: Callable[[Callable, Exception, Any], Any] | None = None,
) -> Any:
    """Thread a value through functions, continuing past stage failures."""
    for f in funcs:
        try:
            value = f(value)
        except Exception as exc:
            if on_error is not None:
                value = on_error(f, exc, value)
    return value


async def async_resilient_pipe(
    value: Any,
    /,
    *funcs: Callable,
    on_error: Callable[[Callable, Exception, Any], Awaitable[Any] | Any] | None = None,
) -> Any:
    """Async version of resilient_pipe for mixed sync/async stages."""
    for f in funcs:
        try:
            result = f(value)
            if inspect.isawaitable(result):
                value = await result
            else:
                value = result
        except Exception as exc:
            if on_error is not None:
                replacement = on_error(f, exc, value)
                if inspect.isawaitable(replacement):
                    value = await replacement
                else:
                    value = replacement
    return value


def when(predicate: Callable[[T], object], fn: Callable[[T], Any]) -> Callable[[T], Any]:
    """Return a stage that applies *fn* only when *predicate* is truthy."""
    def _when(value: T) -> Any:
        if predicate(value):
            return fn(value)
        return value

    _when.__qualname__ = f"when({_callable_name(predicate)}, {_callable_name(fn)})"
    return _when


def traced_pipe(value: Any, /, *funcs: Callable) -> tuple[Any, list[TraceEntry]]:
    """Thread a value through functions and record lightweight trace entries."""
    trace: list[TraceEntry] = []
    for f in funcs:
        before = value
        start = perf_counter()
        value = f(value)
        trace.append(
            TraceEntry(
                _callable_name(f),
                _value_changed(before, value),
                (perf_counter() - start) * 1000.0,
            )
        )
    return value, trace


async def async_traced_pipe(value: Any, /, *funcs: Callable) -> tuple[Any, list[TraceEntry]]:
    """Async version of traced_pipe for mixed sync/async stages."""
    trace: list[TraceEntry] = []
    for f in funcs:
        before = value
        start = perf_counter()
        result = f(value)
        if inspect.isawaitable(result):
            value = await result
        else:
            value = result
        trace.append(
            TraceEntry(
                _callable_name(f),
                _value_changed(before, value),
                (perf_counter() - start) * 1000.0,
            )
        )
    return value, trace
