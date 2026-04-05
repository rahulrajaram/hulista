"""Adapters between TaskOutcome and fp-combinators Result.

fp-combinators is an *optional* dependency.  All imports from that package are
deferred to the function bodies so that importing this module does not require
fp-combinators to be installed.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, TypeVar

from taskgroup_collect._outcome import Failure, Success, TaskOutcome

if TYPE_CHECKING:
    from fp_combinators import Result  # pragma: no cover

T = TypeVar("T")
E = TypeVar("E")


def outcome_to_result(outcome: TaskOutcome[T]) -> Result[T, BaseException]:
    """Convert a :class:`~taskgroup_collect.TaskOutcome` to an fp-combinators ``Result``.

    Parameters
    ----------
    outcome:
        A :class:`~taskgroup_collect.Success` or :class:`~taskgroup_collect.Failure`.

    Returns
    -------
    Result[T, BaseException]
        ``Ok(value)`` for a :class:`~taskgroup_collect.Success`, or
        ``Err(exception)`` for a :class:`~taskgroup_collect.Failure`.

    Raises
    ------
    ImportError
        If ``fp-combinators`` is not installed.
    """
    from fp_combinators import Err, Ok

    if outcome.is_ok:
        return Ok(outcome.unwrap())
    return Err(outcome.unwrap_err())


def result_to_outcome(result: Result[T, E]) -> TaskOutcome[T]:
    """Convert an fp-combinators ``Result`` to a :class:`~taskgroup_collect.TaskOutcome`.

    Parameters
    ----------
    result:
        An ``Ok`` or ``Err`` from fp-combinators.  When the result is ``Err``,
        the contained value **must** be a :class:`BaseException` instance.

    Returns
    -------
    TaskOutcome[T]
        :class:`~taskgroup_collect.Success` for ``Ok``, or
        :class:`~taskgroup_collect.Failure` for ``Err``.

    Raises
    ------
    ImportError
        If ``fp-combinators`` is not installed.
    TypeError
        If the ``Err`` value is not a :class:`BaseException` instance.
    """
    from fp_combinators import Ok as FpOk

    if isinstance(result, FpOk):
        return Success(result.value)
    exc = result.unwrap_err()
    if not isinstance(exc, BaseException):
        raise TypeError(
            f"result_to_outcome requires Err to contain a BaseException, "
            f"got {type(exc).__name__}"
        )
    return Failure(exc)


def outcomes_to_results(
    outcomes: Iterable[TaskOutcome[T]],
) -> list[Result[T, BaseException]]:
    """Convert an iterable of :class:`~taskgroup_collect.TaskOutcome` to a list of ``Result``.

    Parameters
    ----------
    outcomes:
        An iterable of :class:`~taskgroup_collect.Success` or
        :class:`~taskgroup_collect.Failure` instances.

    Returns
    -------
    list[Result[T, BaseException]]
        One ``Result`` per outcome, in the same order.

    Raises
    ------
    ImportError
        If ``fp-combinators`` is not installed.
    """
    return [outcome_to_result(o) for o in outcomes]


__all__ = ["outcome_to_result", "result_to_outcome", "outcomes_to_results"]
