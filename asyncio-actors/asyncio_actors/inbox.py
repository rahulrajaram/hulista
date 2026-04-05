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
    __slots__ = ('_queue', '_stash', '_maxsize', '_policy', '_waiters', '_closed', '_not_full')

    def __init__(self, maxsize: int = 100, policy: OverflowPolicy = OverflowPolicy.BLOCK):
        self._maxsize = maxsize
        self._policy = policy
        self._queue: deque[T] = deque()
        self._stash: deque[T] = deque()
        self._waiters: deque[asyncio.Future[T]] = deque()
        self._closed = False
        self._not_full = asyncio.Event()
        self._not_full.set()  # Initially not full

    @property
    def size(self) -> int:
        return len(self._stash) + len(self._queue)

    @property
    def full(self) -> bool:
        return self.size >= self._maxsize

    @property
    def empty(self) -> bool:
        return self.size == 0

    async def put(self, message: T) -> None:
        if self._closed:
            raise RuntimeError("Inbox is closed")

        if self.full:
            if self._policy == OverflowPolicy.DROP_OLDEST:
                self._drop_oldest()
            elif self._policy == OverflowPolicy.RAISE:
                raise InboxFull(f"Inbox full ({self._maxsize} messages)")
            elif self._policy == OverflowPolicy.BLOCK:
                self._not_full.clear()
                while self.full and not self._closed:
                    await self._not_full.wait()
                    if self.full and not self._closed:
                        self._not_full.clear()
                if self._closed:
                    raise RuntimeError("Inbox closed while waiting")

        self._queue.append(message)
        if self.full:
            self._not_full.clear()
        self._notify_waiters()

    async def get(self, timeout: float | None = None) -> T:
        if self._stash:
            msg = self._stash.popleft()
            if not self.full:
                self._not_full.set()
            return msg
        if self._queue:
            msg = self._queue.popleft()
            if not self.full:
                self._not_full.set()
            return msg
        if self._closed:
            raise RuntimeError("Inbox is closed and empty")

        return await self._await_queued_message(timeout=timeout)

    def _notify_waiters(self) -> None:
        while self._waiters and self._queue:
            fut = self._waiters.popleft()
            if not fut.done():
                msg = self._queue.popleft()
                fut.set_result(msg)
                if not self.full:
                    self._not_full.set()

    def close(self) -> None:
        self._closed = True
        self._not_full.set()  # Unblock any waiting put()
        while self._waiters:
            fut = self._waiters.popleft()
            if not fut.done():
                fut.set_exception(RuntimeError("Inbox closed"))

    def _drop_oldest(self) -> None:
        if self._stash:
            self._stash.popleft()
        elif self._queue:
            self._queue.popleft()

    async def _await_queued_message(self, timeout: float | None = None) -> T:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[T] = loop.create_future()
        self._waiters.append(fut)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            try:
                self._waiters.remove(fut)
            except ValueError:
                pass
            raise

    async def receive(self, match: type, timeout: float | None = None) -> Any:
        """Selective receive: scan inbox for the first message matching a type.

        Non-matching messages are left in the queue for later.
        This implements Erlang-style selective receive for request/response
        correlation and typed message handling.

        Args:
            match: The type to match against.
            timeout: Optional timeout in seconds.

        Returns:
            The first message that is an instance of *match*.

        Raises:
            asyncio.TimeoutError: If no matching message arrives within timeout.
        """
        matched = self._take_matching(self._stash, match)
        if matched is not _SENTINEL:
            if not self.full:
                self._not_full.set()
            return matched
        matched = self._take_matching(self._queue, match)
        if matched is not _SENTINEL:
            if not self.full:
                self._not_full.set()
            return matched

        # No match in queue — wait for new messages
        deadline = None
        if timeout is not None:
            import time
            deadline = time.monotonic() + timeout

        while True:
            remaining = None
            if deadline is not None:
                import time
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError()

            msg = await self._await_queued_message(timeout=remaining)
            if isinstance(msg, match):
                if not self.full:
                    self._not_full.set()
                return msg
            self._stash.append(msg)

    def drain_into(self, other: Inbox[T]) -> int:
        """Drain remaining messages into another inbox (synchronous, no await).

        Returns the number of messages transferred.
        """
        count = 0
        while self._stash:
            msg = self._stash.popleft()
            other._queue.append(msg)
            count += 1
        while self._queue:
            msg = self._queue.popleft()
            other._queue.append(msg)
            count += 1
        return count

    def _take_matching(self, store: deque[T], match: type) -> object:
        for i, msg in enumerate(store):
            if isinstance(msg, match):
                del store[i]
                return msg
        return _SENTINEL


_SENTINEL = object()
