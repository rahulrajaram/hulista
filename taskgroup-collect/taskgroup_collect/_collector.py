"""CollectorTaskGroup — run all tasks to completion, collect all errors."""

from __future__ import annotations

import asyncio
import asyncio.futures as _futures_mod
from typing import Any, Coroutine, TypeVar

from taskgroup_collect._outcome import Failure, Success, TaskOutcome

T = TypeVar("T")


class CollectorTaskGroup:
    """An asyncio.TaskGroup that does NOT cancel siblings on first error.

    All tasks run to completion.  If any raised, ``__aexit__`` raises a
    ``BaseExceptionGroup`` containing every collected exception — the same
    type that stdlib TaskGroup uses.

    Parameters
    ----------
    limit:
        Optional maximum number of tasks that may execute concurrently.
        ``None`` (default) means no limit — identical to the original
        behaviour.

    Usage::

        async with CollectorTaskGroup() as tg:
            t1 = tg.create_task(fetch_a())
            t2 = tg.create_task(fetch_b())
            t3 = tg.create_task(fetch_c())
        # Raises BaseExceptionGroup if any task failed.
        # All three tasks always run to completion.
        # Individual results: t1.result(), t2.result(), etc.
        # Outcomes in creation order: tg.outcomes()

    Deliberately differs from stdlib ``asyncio.TaskGroup`` in two ways:
    child failure does not cancel siblings, and it also does not interrupt
    the still-running ``async with`` body. External cancellation of the
    parent task still propagates cancellation to children normally.

    Ref: https://github.com/python/cpython/issues/101581
    """

    def __init__(self, *, limit: int | None = None) -> None:
        if limit is not None and limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit!r}")
        self._limit = limit
        self._semaphore: asyncio.Semaphore | None = None

        self._entered = False
        self._exiting = False
        self._aborting = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._parent_task: asyncio.Task[Any] | None = None
        self._parent_cancel_requested = False
        self._tasks: set[asyncio.Task[Any]] = set()
        self._errors: list[BaseException] = []
        self._base_error: BaseException | None = None
        self._on_completed_fut: asyncio.Future[bool] | None = None

        # Outcome tracking — parallel list to creation order.
        # Each entry is (task, index) so we can fill _outcomes in order.
        self._task_order: list[asyncio.Task[Any]] = []
        self._outcomes_result: list[TaskOutcome[Any]] | None = None

    def __repr__(self) -> str:
        info = ['']
        if self._tasks:
            info.append(f'tasks={len(self._tasks)}')
        if self._errors:
            info.append(f'errors={len(self._errors)}')
        if self._aborting:
            info.append('cancelling')
        elif self._entered:
            info.append('entered')
        if self._limit is not None:
            info.append(f'limit={self._limit}')
        info_str = ' '.join(info)
        return f'<CollectorTaskGroup{info_str}>'

    async def __aenter__(self) -> CollectorTaskGroup:
        if self._entered:
            raise RuntimeError(
                f"CollectorTaskGroup {self!r} has already been entered")
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        self._parent_task = asyncio.current_task()
        if self._parent_task is None:
            raise RuntimeError(
                f'CollectorTaskGroup {self!r} cannot determine the parent task')
        if self._limit is not None:
            self._semaphore = asyncio.Semaphore(self._limit)
        self._entered = True
        return self

    async def __aexit__(
        self,
        et: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool | None:
        try:
            return await self._aexit(et, exc)
        finally:
            self._parent_task = None
            self._errors = None  # type: ignore[assignment]
            self._base_error = None
            exc = None

    async def _aexit(
        self,
        et: type[BaseException] | None,
        exc: BaseException | None,
    ) -> bool | None:
        self._exiting = True

        if (exc is not None
                and self._is_base_error(exc)
                and self._base_error is None):
            self._base_error = exc

        if et is not None and issubclass(et, asyncio.CancelledError):
            propagate_cancellation_error: BaseException | None = exc
        else:
            propagate_cancellation_error = None

        if et is not None:
            if not self._aborting:
                # Parent is being cancelled or raised — abort children.
                self._abort()

        # Wait for all tasks to finish.
        while self._tasks:
            if self._on_completed_fut is None:
                self._on_completed_fut = self._loop.create_future()  # type: ignore[union-attr]
            try:
                await self._on_completed_fut
            except asyncio.CancelledError as ex:
                if not self._aborting:
                    propagate_cancellation_error = ex
                    self._abort()
            self._on_completed_fut = None

        if self._tasks:
            raise RuntimeError("CollectorTaskGroup failed to drain all tasks before exit")

        # Build the outcomes list in creation order before clearing state.
        self._outcomes_result = []
        for task in self._task_order:
            if task.cancelled():
                # Treat a cancelled task as a Failure with CancelledError.
                self._outcomes_result.append(
                    Failure(asyncio.CancelledError())
                )
            elif task.exception() is not None:
                self._outcomes_result.append(Failure(task.exception()))  # type: ignore[arg-type]
            else:
                self._outcomes_result.append(Success(task.result()))

        if self._base_error is not None:
            try:
                raise self._base_error
            finally:
                exc = None

        if self._parent_cancel_requested:
            if self._parent_task.uncancel() == 0:  # type: ignore[union-attr]
                propagate_cancellation_error = None

        try:
            if propagate_cancellation_error is not None and not self._errors:
                try:
                    raise propagate_cancellation_error
                finally:
                    exc = None
        finally:
            propagate_cancellation_error = None

        if et is not None and not issubclass(et, asyncio.CancelledError):
            self._errors.append(exc)  # type: ignore[arg-type]

        if self._errors:
            if self._parent_task.cancelling():  # type: ignore[union-attr]
                self._parent_task.uncancel()  # type: ignore[union-attr]
                self._parent_task.cancel()  # type: ignore[union-attr]
            try:
                raise BaseExceptionGroup(
                    'unhandled errors in a CollectorTaskGroup',
                    self._errors,
                ) from None
            finally:
                exc = None

        return None

    def create_task(
        self,
        coro: Coroutine[Any, Any, T],
        **kwargs: Any,
    ) -> asyncio.Task[T]:
        """Create a new task in this group and return it."""
        if not self._entered:
            coro.close()
            raise RuntimeError(f"CollectorTaskGroup {self!r} has not been entered")
        if self._exiting and not self._tasks:
            coro.close()
            raise RuntimeError(f"CollectorTaskGroup {self!r} is finished")
        if self._aborting:
            coro.close()
            raise RuntimeError(f"CollectorTaskGroup {self!r} is shutting down")

        if self._semaphore is not None:
            # Wrap the coroutine so it acquires the semaphore before running.
            coro = self._with_semaphore(self._semaphore, coro)  # type: ignore[assignment]

        task: asyncio.Task[T] = self._loop.create_task(coro, **kwargs)  # type: ignore[union-attr]

        # Track awaited-by relationship if available (3.12+).
        if hasattr(_futures_mod, 'future_add_to_awaited_by'):
            _futures_mod.future_add_to_awaited_by(task, self._parent_task)

        self._tasks.add(task)
        self._task_order.append(task)
        task.add_done_callback(self._on_task_done)
        try:
            return task
        finally:
            del task

    @staticmethod
    async def _with_semaphore(
        sem: asyncio.Semaphore,
        coro: Coroutine[Any, Any, T],
    ) -> T:
        """Acquire *sem* before awaiting *coro*, then release on exit."""
        async with sem:
            return await coro

    def outcomes(self) -> list[TaskOutcome[Any]]:
        """Return per-task outcomes in creation order.

        Must be called after the ``async with`` block has exited.  Returns
        a :class:`~taskgroup_collect.Success` for every task that returned
        normally and a :class:`~taskgroup_collect.Failure` for every task
        that raised (or was cancelled).

        Raises
        ------
        RuntimeError
            If called before the group has exited.
        """
        if self._outcomes_result is None:
            raise RuntimeError(
                "outcomes() may only be called after the CollectorTaskGroup "
                "has exited its 'async with' block"
            )
        return list(self._outcomes_result)

    def _is_base_error(self, exc: BaseException) -> bool:
        return isinstance(exc, (SystemExit, KeyboardInterrupt))

    def _abort(self) -> None:
        self._aborting = True
        for t in self._tasks:
            if not t.done():
                t.cancel()

    def _on_task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)

        if hasattr(_futures_mod, 'future_discard_from_awaited_by'):
            _futures_mod.future_discard_from_awaited_by(task, self._parent_task)

        if self._on_completed_fut is not None and not self._tasks:
            if not self._on_completed_fut.done():
                self._on_completed_fut.set_result(True)

        if task.cancelled():
            return

        exc = task.exception()
        if exc is None:
            return

        # KEY DIFFERENCE: collect the error but do NOT abort.
        self._errors.append(exc)
        if self._is_base_error(exc) and self._base_error is None:
            self._base_error = exc

        # Intentionally no self._abort() here — let siblings keep running.
