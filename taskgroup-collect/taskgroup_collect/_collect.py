"""collect_results — convenience wrapper for running coroutines with CollectorTaskGroup."""

from __future__ import annotations

from collections.abc import Coroutine, Iterable
from typing import Any, TypeVar

from taskgroup_collect._collector import CollectorTaskGroup
from taskgroup_collect._outcome import TaskOutcome

T = TypeVar("T")


async def collect_results(
    coros: Iterable[Coroutine[Any, Any, T]],
    *,
    limit: int | None = None,
) -> list[TaskOutcome[T]]:
    """Run all coroutines concurrently and return their outcomes.

    A convenience wrapper around :class:`~taskgroup_collect.CollectorTaskGroup`
    that takes an iterable of coroutines, runs them all to completion (no
    sibling cancellation on first error), and returns a
    ``list[TaskOutcome[T]]`` in the same order as the input iterable.

    Unlike using :class:`~taskgroup_collect.CollectorTaskGroup` directly, this
    function **never raises** :exc:`BaseExceptionGroup` — failures are captured
    as :class:`~taskgroup_collect.Failure` entries in the returned list.

    Parameters
    ----------
    coros:
        An iterable of coroutines to run.  Materialised immediately so that
        creation order is preserved regardless of iterator type.
    limit:
        Optional maximum number of coroutines that may execute concurrently.
        ``None`` (default) means no limit.

    Returns
    -------
    list[TaskOutcome[T]]
        One entry per input coroutine, in creation order.
        Each entry is either a :class:`~taskgroup_collect.Success` (task
        returned normally) or a :class:`~taskgroup_collect.Failure` (task
        raised an exception).

    Examples
    --------
    ::

        async def fetch(url: str) -> str:
            ...

        outcomes = await collect_results([fetch(u) for u in urls])
        results = [o.unwrap() for o in outcomes if o.is_ok]
    """
    coro_list = list(coros)  # materialise to preserve ordering
    tg = CollectorTaskGroup(limit=limit)
    try:
        async with tg:
            for c in coro_list:
                tg.create_task(c)
    except BaseExceptionGroup:
        pass  # errors are captured as Failure outcomes; no re-raise needed
    return tg.outcomes()


__all__ = ["collect_results"]
