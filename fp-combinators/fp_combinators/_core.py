"""Lightweight FP combinators for Python."""
from __future__ import annotations
from typing import TypeVar, Callable, Any

T = TypeVar('T')


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

    def _composed(*args, **kwargs):
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

    def _first(*args, **kwargs):
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

    def _pipeline(*args, **kwargs):
        result = funcs[0](*args, **kwargs)
        for f in funcs[1:]:
            result = f(result)
        return result

    _pipeline.__qualname__ = ' | '.join(
        getattr(f, '__qualname__', repr(f)) for f in funcs
    )
    return _pipeline
