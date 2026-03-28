from __future__ import annotations

import asyncio

import pytest

from asyncio_actors.inbox import Inbox, OverflowPolicy


@pytest.mark.asyncio
async def test_close_unblocks_blocked_put() -> None:
    inbox: Inbox[int] = Inbox(maxsize=1, policy=OverflowPolicy.BLOCK)
    await inbox.put(1)

    task = asyncio.create_task(inbox.put(2))
    await asyncio.sleep(0.01)
    inbox.close()

    with pytest.raises(RuntimeError, match="closed while waiting"):
        await task


@pytest.mark.asyncio
async def test_get_prefers_stash_and_reopens_capacity() -> None:
    inbox: Inbox[int] = Inbox(maxsize=2)
    inbox._stash.append(10)
    await inbox.put(20)

    assert inbox.full is True
    assert await inbox.get() == 10
    assert inbox.full is False
    assert await inbox.get() == 20


@pytest.mark.asyncio
async def test_receive_timeout_cleans_waiter() -> None:
    inbox: Inbox[str] = Inbox(maxsize=1)
    with pytest.raises(asyncio.TimeoutError):
        await inbox.receive(int, timeout=0.01)
    assert list(inbox._waiters) == []


@pytest.mark.asyncio
async def test_drop_oldest_prefers_stash() -> None:
    inbox: Inbox[int] = Inbox(maxsize=2, policy=OverflowPolicy.DROP_OLDEST)
    inbox._stash.append(1)
    await inbox.put(2)

    await inbox.put(3)

    assert await inbox.get() == 2
    assert await inbox.get() == 3


def test_notify_waiters_skips_completed_futures() -> None:
    inbox: Inbox[int] = Inbox(maxsize=2)
    loop = asyncio.new_event_loop()
    try:
        done_future = loop.create_future()
        done_future.set_result(99)
        waiting_future = loop.create_future()
        inbox._waiters.append(done_future)
        inbox._waiters.append(waiting_future)
        inbox._queue.append(1)

        inbox._notify_waiters()

        assert waiting_future.result() == 1
        assert list(inbox._waiters) == []
    finally:
        loop.close()


def test_drain_into_moves_stash_before_queue() -> None:
    source: Inbox[int] = Inbox(maxsize=4)
    target: Inbox[int] = Inbox(maxsize=4)

    source._stash.extend([1, 2])
    source._queue.extend([3, 4])

    assert source.drain_into(target) == 4
    assert list(target._queue) == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_receive_timeout_after_stashing_unmatched_message() -> None:
    inbox: Inbox[object] = Inbox(maxsize=2)

    waiter = asyncio.create_task(inbox.receive(int, timeout=0.02))
    await asyncio.sleep(0)
    await inbox.put("unmatched")

    with pytest.raises(asyncio.TimeoutError):
        await waiter

    assert list(inbox._stash) == ["unmatched"]


def test_close_skips_done_waiters() -> None:
    inbox: Inbox[int] = Inbox(maxsize=1)
    loop = asyncio.new_event_loop()
    try:
        done_future = loop.create_future()
        done_future.set_result(1)
        inbox._waiters.append(done_future)
        inbox.close()
        assert list(inbox._waiters) == []
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_receive_matches_existing_stash_and_queue() -> None:
    stash_inbox: Inbox[object] = Inbox(maxsize=2)
    stash_inbox._stash.append("needle")
    assert await stash_inbox.receive(str) == "needle"

    queue_inbox: Inbox[object] = Inbox(maxsize=2)
    await queue_inbox.put("needle")
    assert await queue_inbox.receive(str) == "needle"


def test_get_from_overfilled_internal_buffers_can_stay_full() -> None:
    stash_inbox: Inbox[int] = Inbox(maxsize=1)
    stash_inbox._stash.extend([1, 2])
    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(stash_inbox.get()) == 1
        assert stash_inbox.full is True
    finally:
        loop.close()

    queue_inbox: Inbox[int] = Inbox(maxsize=1)
    queue_inbox._queue.extend([1, 2])
    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(queue_inbox.get()) == 1
        assert queue_inbox.full is True
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_await_queued_message_timeout_after_waiter_removed() -> None:
    inbox: Inbox[int] = Inbox(maxsize=1)
    task = asyncio.create_task(inbox._await_queued_message(timeout=0.01))
    await asyncio.sleep(0)
    inbox._waiters.popleft()
    with pytest.raises(asyncio.TimeoutError):
        await task
