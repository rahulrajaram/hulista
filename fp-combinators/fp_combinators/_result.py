"""Result type for typed error handling without exceptions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

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
            return self.value
        raise ValueError(f"Called unwrap() on Err: {self.error!r}")

    def unwrap_or(self, default: T) -> T:
        """Return the Ok value, or a default if Err."""
        if isinstance(self, Ok):
            return self.value
        return default

    def unwrap_err(self) -> E:
        """Return the Err value, or raise if Ok."""
        if isinstance(self, Err):
            return self.error
        raise ValueError(f"Called unwrap_err() on Ok: {self.value!r}")

    def map(self, f: Callable[[T], U]) -> Result[U, E]:
        """Apply f to the Ok value, or pass through Err."""
        if isinstance(self, Ok):
            return Ok(f(self.value))
        return self

    def map_err(self, f: Callable[[E], U]) -> Result[T, U]:
        """Apply f to the Err value, or pass through Ok."""
        if isinstance(self, Err):
            return Err(f(self.error))
        return self

    def and_then(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Chain a computation that may fail (flatmap)."""
        if isinstance(self, Ok):
            return f(self.value)
        return self

    def or_else(self, f: Callable[[E], Result[T, U]]) -> Result[T, U]:
        """Handle an Err by running an alternative computation."""
        if isinstance(self, Err):
            return f(self.error)
        return self

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
