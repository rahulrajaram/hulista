"""Async-sync bridge for the monitor-thread pattern."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future
from typing import Any, Callable, Coroutine, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class PersistentBridge:
    """Bridge for calling async code from synchronous threads.

    Uses a persistent event-loop reference and
    :func:`asyncio.run_coroutine_threadsafe` to avoid the overhead of
    spinning up a new event loop (as ``asyncio.run()`` would do) or the
    ``contextvars`` copying overhead of ``asyncio.to_thread()``.

    The bridge does *not* own the event loop; the caller is responsible for
    keeping the loop alive for as long as the bridge is in use.

    Usage::

        # In the thread that owns the event loop:
        bridge = PersistentBridge(asyncio.get_event_loop())

        # From any other (synchronous) thread:
        bridge.call(some_async_func, arg1, arg2)          # fire-and-forget
        result = bridge.call_wait(some_async_func, arg1)  # blocking wait
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def call(
        self, coro_func: Callable[..., Coroutine[Any, Any, Any]], *args: Any
    ) -> None:
        """Schedule an async call from a sync thread; do not wait for result."""
        future = asyncio.run_coroutine_threadsafe(coro_func(*args), self._loop)
        future.add_done_callback(self._log_call_exception)

    def call_wait(
        self,
        coro_func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        timeout: float | None = None,
    ) -> T:
        """Schedule an async call from a sync thread and block until complete.

        Args:
            coro_func: An async callable.
            *args: Positional arguments forwarded to *coro_func*.
            timeout: Optional timeout in seconds passed to
                :meth:`concurrent.futures.Future.result`.

        Returns:
            The return value of the coroutine.

        Raises:
            concurrent.futures.TimeoutError: If *timeout* elapses.
            Exception: Any exception raised inside the coroutine.
        """
        future = asyncio.run_coroutine_threadsafe(coro_func(*args), self._loop)
        return future.result(timeout=timeout)

    @staticmethod
    def _log_call_exception(future: Future[Any]) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("PersistentBridge.call() task failed")
