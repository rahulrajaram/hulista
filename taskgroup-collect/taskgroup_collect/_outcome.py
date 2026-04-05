"""TaskOutcome — a typed result wrapper for CollectorTaskGroup task results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, NoReturn, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Success(Generic[T]):
    """A task completed successfully and returned *value*."""

    value: T

    @property
    def is_ok(self) -> bool:
        """Return True — this is a successful outcome."""
        return True

    @property
    def is_err(self) -> bool:
        """Return False — this is not a failure outcome."""
        return False

    def unwrap(self) -> T:
        """Return the contained value."""
        return self.value

    def unwrap_err(self) -> NoReturn:
        """Raise TypeError — a Success has no exception."""
        raise TypeError("called unwrap_err() on a Success outcome")


@dataclass(frozen=True)
class Failure(Generic[T]):
    """A task raised *exception*."""

    exception: BaseException

    @property
    def is_ok(self) -> bool:
        """Return False — this is not a successful outcome."""
        return False

    @property
    def is_err(self) -> bool:
        """Return True — this is a failure outcome."""
        return True

    def unwrap(self) -> NoReturn:
        """Raise the contained exception."""
        raise self.exception

    def unwrap_err(self) -> BaseException:
        """Return the contained exception."""
        return self.exception


# Union type used as the public API.
TaskOutcome = Success[T] | Failure[T]

__all__ = ["TaskOutcome", "Success", "Failure"]
