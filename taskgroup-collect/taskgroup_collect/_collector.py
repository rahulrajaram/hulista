"""CollectorTaskGroup — run all tasks to completion, collect all errors."""

from __future__ import annotations

import asyncio
import asyncio.futures as _futures_mod


class CollectorTaskGroup:
    """An asyncio.TaskGroup that does NOT cancel siblings on first error.

    All tasks run to completion.  If any raised, ``__aexit__`` raises a
    ``BaseExceptionGroup`` containing every collected exception — the same
    type that stdlib TaskGroup uses.

    Usage::

        async with CollectorTaskGroup() as tg:
            t1 = tg.create_task(fetch_a())
            t2 = tg.create_task(fetch_b())
            t3 = tg.create_task(fetch_c())
        # Raises BaseExceptionGroup if any task failed.
        # All three tasks always run to completion.
        # Individual results: t1.result(), t2.result(), etc.

    Deliberately differs from stdlib ``asyncio.TaskGroup`` in two ways:
    child failure does not cancel siblings, and it also does not interrupt
    the still-running ``async with`` body. External cancellation of the
    parent task still propagates cancellation to children normally.

    Ref: https://github.com/python/cpython/issues/101581
    """

    def __init__(self):
        self._entered = False
        self._exiting = False
        self._aborting = False
        self._loop = None
        self._parent_task = None
        self._parent_cancel_requested = False
        self._tasks: set[asyncio.Task] = set()
        self._errors: list[BaseException] = []
        self._base_error = None
        self._on_completed_fut = None

    def __repr__(self):
        info = ['']
        if self._tasks:
            info.append(f'tasks={len(self._tasks)}')
        if self._errors:
            info.append(f'errors={len(self._errors)}')
        if self._aborting:
            info.append('cancelling')
        elif self._entered:
            info.append('entered')
        info_str = ' '.join(info)
        return f'<CollectorTaskGroup{info_str}>'

    async def __aenter__(self):
        if self._entered:
            raise RuntimeError(
                f"CollectorTaskGroup {self!r} has already been entered")
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        self._parent_task = asyncio.current_task()
        if self._parent_task is None:
            raise RuntimeError(
                f'CollectorTaskGroup {self!r} cannot determine the parent task')
        self._entered = True
        return self

    async def __aexit__(self, et, exc, tb):
        try:
            return await self._aexit(et, exc)
        finally:
            self._parent_task = None
            self._errors = None
            self._base_error = None
            exc = None

    async def _aexit(self, et, exc):
        self._exiting = True

        if (exc is not None
                and self._is_base_error(exc)
                and self._base_error is None):
            self._base_error = exc

        if et is not None and issubclass(et, asyncio.CancelledError):
            propagate_cancellation_error = exc
        else:
            propagate_cancellation_error = None

        if et is not None:
            if not self._aborting:
                # Parent is being cancelled or raised — abort children.
                self._abort()

        # Wait for all tasks to finish.
        while self._tasks:
            if self._on_completed_fut is None:
                self._on_completed_fut = self._loop.create_future()
            try:
                await self._on_completed_fut
            except asyncio.CancelledError as ex:
                if not self._aborting:
                    propagate_cancellation_error = ex
                    self._abort()
            self._on_completed_fut = None

        assert not self._tasks

        if self._base_error is not None:
            try:
                raise self._base_error
            finally:
                exc = None

        if self._parent_cancel_requested:
            if self._parent_task.uncancel() == 0:
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
            self._errors.append(exc)

        if self._errors:
            if self._parent_task.cancelling():
                self._parent_task.uncancel()
                self._parent_task.cancel()
            try:
                raise BaseExceptionGroup(
                    'unhandled errors in a CollectorTaskGroup',
                    self._errors,
                ) from None
            finally:
                exc = None

    def create_task(self, coro, **kwargs):
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
        task = self._loop.create_task(coro, **kwargs)

        # Track awaited-by relationship if available (3.12+).
        if hasattr(_futures_mod, 'future_add_to_awaited_by'):
            _futures_mod.future_add_to_awaited_by(task, self._parent_task)

        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        try:
            return task
        finally:
            del task

    def _is_base_error(self, exc: BaseException) -> bool:
        return isinstance(exc, (SystemExit, KeyboardInterrupt))

    def _abort(self):
        self._aborting = True
        for t in self._tasks:
            if not t.done():
                t.cancel()

    def _on_task_done(self, task):
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
