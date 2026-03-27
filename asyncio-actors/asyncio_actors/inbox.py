"""Bounded inbox with back-pressure policies."""
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Generic, TypeVar
from collections import deque

T = TypeVar('T')


class OverflowPolicy(Enum):
    BLOCK = "block"              # Block sender until space available
    DROP_OLDEST = "drop_oldest"  # Drop oldest message to make room
    RAISE = "raise"              # Raise InboxFull exception


class InboxFull(Exception):
    pass


class Inbox(Generic[T]):
    """Bounded message inbox with configurable overflow policy."""
    __slots__ = ('_queue', '_maxsize', '_policy', '_waiters', '_closed')

    def __init__(self, maxsize: int = 100, policy: OverflowPolicy = OverflowPolicy.BLOCK):
        self._maxsize = maxsize
        self._policy = policy
        self._queue: deque[T] = deque()
        self._waiters: deque[asyncio.Future[T]] = deque()
        self._closed = False

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def full(self) -> bool:
        return len(self._queue) >= self._maxsize

    @property
    def empty(self) -> bool:
        return len(self._queue) == 0

    async def put(self, message: T) -> None:
        if self._closed:
            raise RuntimeError("Inbox is closed")

        if self.full:
            if self._policy == OverflowPolicy.DROP_OLDEST:
                self._queue.popleft()
            elif self._policy == OverflowPolicy.RAISE:
                raise InboxFull(f"Inbox full ({self._maxsize} messages)")
            elif self._policy == OverflowPolicy.BLOCK:
                while self.full and not self._closed:
                    await asyncio.sleep(0.001)
                if self._closed:
                    raise RuntimeError("Inbox closed while waiting")

        self._queue.append(message)
        self._notify_waiters()

    async def get(self, timeout: float | None = None) -> T:
        if self._queue:
            return self._queue.popleft()
        if self._closed:
            raise RuntimeError("Inbox is closed and empty")

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[T] = loop.create_future()
        self._waiters.append(fut)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            # Remove the future from waiters if still present
            try:
                self._waiters.remove(fut)
            except ValueError:
                pass
            raise

    def _notify_waiters(self) -> None:
        while self._waiters and self._queue:
            fut = self._waiters.popleft()
            if not fut.done():
                fut.set_result(self._queue.popleft())

    def close(self) -> None:
        self._closed = True
        while self._waiters:
            fut = self._waiters.popleft()
            if not fut.done():
                fut.set_exception(RuntimeError("Inbox closed"))
