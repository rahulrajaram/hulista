"""Result type for typed error handling without exceptions."""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast

T = TypeVar('T')
E = TypeVar('E')
U = TypeVar('U')


class Result(Generic[T, E]):
    """Base class for Ok and Err. Represents a computation that may fail."""

    def is_ok(self) -> bool:
        return isinstance(self, Ok)

    def is_err(self) -> bool:
        return isinstance(self, Err)

    def unwrap(self) -> T:
        """Return the Ok value, or raise if Err."""
        if isinstance(self, Ok):
            ok = cast(Ok[T, E], self)
            return ok.value
        err = cast(Err[T, E], self)
        raise ValueError(f"Called unwrap() on Err: {err.error!r}")

    def unwrap_or(self, default: T) -> T:
        """Return the Ok value, or a default if Err."""
        if isinstance(self, Ok):
            ok = cast(Ok[T, E], self)
            return ok.value
        return default

    def unwrap_err(self) -> E:
        """Return the Err value, or raise if Ok."""
        if isinstance(self, Err):
            err = cast(Err[T, E], self)
            return err.error
        ok = cast(Ok[T, E], self)
        raise ValueError(f"Called unwrap_err() on Ok: {ok.value!r}")

    def map(self, f: Callable[[T], U]) -> Result[U, E]:
        """Apply f to the Ok value, or pass through Err."""
        if isinstance(self, Ok):
            return Ok(f(self.value))
        return cast(Result[U, E], self)

    def map_err(self, f: Callable[[E], U]) -> Result[T, U]:
        """Apply f to the Err value, or pass through Ok."""
        if isinstance(self, Err):
            return Err(f(self.error))
        return cast(Result[T, U], self)

    def and_then(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Chain a computation that may fail (flatmap)."""
        if isinstance(self, Ok):
            return f(self.value)
        return cast(Result[U, E], self)

    def or_else(self, f: Callable[[E], Result[T, U]]) -> Result[T, U]:
        """Handle an Err by running an alternative computation."""
        if isinstance(self, Err):
            return f(self.error)
        return cast(Result[T, U], self)

    async def async_map(self, f: Callable[[T], Awaitable[U]]) -> Result[U, E]:
        """Apply an async function to the Ok value, or pass through Err."""
        if isinstance(self, Ok):
            return Ok(await f(self.value))
        return cast(Result[U, E], self)

    async def async_and_then(
        self, f: Callable[[T], Awaitable[Result[U, E]]]
    ) -> Result[U, E]:
        """Chain an async computation that itself returns a Result (async flatmap)."""
        if isinstance(self, Ok):
            return await f(self.value)
        return cast(Result[U, E], self)

    @classmethod
    async def from_awaitable(cls, aw: Awaitable[T]) -> Result[T, Exception]:
        """Await *aw* and wrap the result in Ok, or catch any exception as Err."""
        try:
            return Ok(await aw)
        except Exception as exc:
            return Err(exc)

    @classmethod
    def from_call(
        cls,
        func: Callable[..., T],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Result[T, Exception]:
        """Call *func* with the given arguments; wrap the return value in Ok,
        or catch any raised exception as Err.
        """
        try:
            return Ok(func(*args, **kwargs))
        except Exception as exc:
            return Err(exc)

    def __bool__(self) -> bool:
        return self.is_ok()


@dataclass(frozen=True, slots=True)
class Ok(Result[T, E]):
    """Successful result."""
    value: T

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass(frozen=True, slots=True)
class Err(Result[T, E]):
    """Error result."""
    error: E

    def __repr__(self) -> str:
        return f"Err({self.error!r})"


def try_pipe(value: Any, /, *funcs: Callable) -> Result:
    """Thread a value through functions, catching exceptions as Err.

    Like pipe(), but wraps the pipeline in error handling.
    Each function receives the raw value (not a Result).
    If any function raises, returns Err(exception).
    On success, returns Ok(final_value).

    Usage:
        result = try_pipe("42", int, lambda x: x * 2)
        # Ok(84)

        result = try_pipe("not a number", int, lambda x: x * 2)
        # Err(ValueError("invalid literal ..."))
    """
    for f in funcs:
        try:
            value = f(value)
        except Exception as e:
            return Err(e)
    return Ok(value)


async def async_try_pipe(value: Any, /, *funcs: Callable) -> Result:
    """Async version of try_pipe — handles both sync and async functions.

    Like async_pipe(), but wraps the pipeline in error handling.
    If any function raises (or an awaited coroutine raises), returns Err(exception).
    On success, returns Ok(final_value).

    Usage:
        result = await async_try_pipe("42", int, async_validate)
        # Ok(validated_value) or Err(exception)
    """
    for f in funcs:
        try:
            result = f(value)
            if inspect.isawaitable(result):
                value = await result
            else:
                value = result
        except Exception as e:
            return Err(e)
    return Ok(value)


def sequence(results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    """Collect an iterable of Results into a single Result of a list.

    Returns ``Ok(list_of_values)`` when every element is ``Ok``,
    or the first ``Err`` encountered (short-circuiting).

    Usage::

        sequence([Ok(1), Ok(2), Ok(3)])   # Ok([1, 2, 3])
        sequence([Ok(1), Err("bad"), Ok(3)])  # Err("bad")
    """
    values: list[T] = []
    for r in results:
        if isinstance(r, Err):
            return cast(Result[list[T], E], r)
        values.append(cast(Ok[T, E], r).value)
    return Ok(values)


def traverse(
    items: Iterable[T],
    func: Callable[[T], Result[U, E]],
) -> Result[list[U], E]:
    """Apply *func* to each item, collecting results into a single Result.

    Returns ``Ok(list_of_mapped_values)`` when *func* succeeds for every item,
    or the first ``Err`` returned by *func* (short-circuiting).

    Usage::

        traverse([1, 2, 3], lambda x: Ok(x * 2))   # Ok([2, 4, 6])
        traverse([1, -1, 3], lambda x: Err("neg") if x < 0 else Ok(x))
        # Err("neg")
    """
    values: list[U] = []
    for item in items:
        r = func(item)
        if isinstance(r, Err):
            return cast(Result[list[U], E], r)
        values.append(cast(Ok[U, E], r).value)
    return Ok(values)
