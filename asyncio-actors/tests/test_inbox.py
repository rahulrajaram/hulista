"""Tests for asyncio_actors.inbox."""
from __future__ import annotations

import asyncio
import pytest

from asyncio_actors.inbox import Inbox, InboxFull, OverflowPolicy


# ---------------------------------------------------------------------------
# Basic put / get
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_basic_put_get():
    inbox: Inbox[int] = Inbox(maxsize=10)
    await inbox.put(1)
    await inbox.put(2)
    assert await inbox.get() == 1
    assert await inbox.get() == 2


@pytest.mark.asyncio
async def test_fifo_ordering():
    inbox: Inbox[str] = Inbox(maxsize=10)
    for word in ("alpha", "beta", "gamma"):
        await inbox.put(word)
    results = [await inbox.get() for _ in range(3)]
    assert results == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_size_and_empty_full_properties():
    inbox: Inbox[int] = Inbox(maxsize=3)
    assert inbox.empty
    assert not inbox.full
    await inbox.put(1)
    assert inbox.size == 1
    await inbox.put(2)
    await inbox.put(3)
    assert inbox.full
    assert not inbox.empty


@pytest.mark.asyncio
async def test_get_blocks_until_message():
    inbox: Inbox[int] = Inbox(maxsize=5)

    async def producer():
        await asyncio.sleep(0.05)
        await inbox.put(42)

    asyncio.create_task(producer())
    value = await asyncio.wait_for(inbox.get(), timeout=1.0)
    assert value == 42


@pytest.mark.asyncio
async def test_get_timeout_raises():
    inbox: Inbox[int] = Inbox(maxsize=5)
    with pytest.raises(asyncio.TimeoutError):
        await inbox.get(timeout=0.01)


# ---------------------------------------------------------------------------
# Overflow policies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overflow_raise_policy():
    inbox: Inbox[int] = Inbox(maxsize=2, policy=OverflowPolicy.RAISE)
    await inbox.put(1)
    await inbox.put(2)
    with pytest.raises(InboxFull):
        await inbox.put(3)
    # Existing messages must be intact.
    assert await inbox.get() == 1
    assert await inbox.get() == 2


@pytest.mark.asyncio
async def test_overflow_drop_oldest_policy():
    inbox: Inbox[int] = Inbox(maxsize=2, policy=OverflowPolicy.DROP_OLDEST)
    await inbox.put(1)
    await inbox.put(2)
    # Putting a third message should drop message 1.
    await inbox.put(3)
    assert inbox.size == 2
    assert await inbox.get() == 2
    assert await inbox.get() == 3


@pytest.mark.asyncio
async def test_overflow_block_policy():
    """BLOCK policy: sender waits until a slot is free."""
    inbox: Inbox[int] = Inbox(maxsize=1, policy=OverflowPolicy.BLOCK)
    await inbox.put(10)  # fills the inbox

    put_done = False

    async def slow_put():
        nonlocal put_done
        await inbox.put(20)
        put_done = True

    task = asyncio.create_task(slow_put())
    # Give slow_put time to spin but not finish.
    await asyncio.sleep(0.02)
    assert not put_done

    # Consume the first message to unblock.
    msg = await inbox.get()
    assert msg == 10
    await asyncio.wait_for(task, timeout=1.0)
    assert put_done
    assert await inbox.get() == 20


# ---------------------------------------------------------------------------
# Close behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_on_closed_inbox_raises():
    inbox: Inbox[int] = Inbox()
    inbox.close()
    with pytest.raises(RuntimeError, match="closed"):
        await inbox.put(1)


@pytest.mark.asyncio
async def test_get_on_closed_empty_inbox_raises():
    inbox: Inbox[int] = Inbox()
    inbox.close()
    with pytest.raises(RuntimeError, match="closed"):
        await inbox.get()


@pytest.mark.asyncio
async def test_get_waiter_unblocked_on_close():
    """A coroutine blocked in get() should receive RuntimeError when closed."""
    inbox: Inbox[int] = Inbox(maxsize=5)

    async def waiter():
        return await inbox.get()

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0.01)  # ensure waiter is blocked
    inbox.close()

    with pytest.raises(RuntimeError, match="closed"):
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_drain_before_close():
    """Messages already in the queue are retrievable before close empties it."""
    inbox: Inbox[str] = Inbox(maxsize=5)
    await inbox.put("hello")
    assert await inbox.get() == "hello"
    inbox.close()
    with pytest.raises(RuntimeError):
        await inbox.get()
