from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import taskgroup_collect._collector as collector_module
from taskgroup_collect import CollectorTaskGroup


def test_repr_includes_runtime_flags() -> None:
    tg = CollectorTaskGroup()
    tg._entered = True
    tg._aborting = True
    tg._tasks = {object()}
    tg._errors = [RuntimeError("boom")]

    rendered = repr(tg)
    assert "tasks=1" in rendered
    assert "errors=1" in rendered
    assert "cancelling" in rendered


@pytest.mark.asyncio
async def test_enter_without_parent_task_raises(monkeypatch) -> None:
    tg = CollectorTaskGroup()
    monkeypatch.setattr(collector_module.asyncio, "current_task", lambda: None)
    with pytest.raises(RuntimeError, match="cannot determine the parent task"):
        await tg.__aenter__()


@pytest.mark.asyncio
async def test_create_task_before_enter_closes_coroutine() -> None:
    tg = CollectorTaskGroup()
    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="has not been entered"):
        tg.create_task(coro)
    assert coro.cr_frame is None


@pytest.mark.asyncio
async def test_create_task_while_aborting_closes_coroutine() -> None:
    tg = CollectorTaskGroup()
    tg._entered = True
    tg._aborting = True
    tg._loop = asyncio.get_running_loop()
    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="shutting down"):
        tg.create_task(coro)
    assert coro.cr_frame is None


@pytest.mark.asyncio
async def test_create_task_tracks_awaited_by_when_available(monkeypatch) -> None:
    tg = CollectorTaskGroup()
    async with tg:
        recorded: list[tuple[asyncio.Task[None], asyncio.Task[object] | None]] = []
        monkeypatch.setattr(
            collector_module._futures_mod,
            "future_add_to_awaited_by",
            lambda task, parent: recorded.append((task, parent)),
            raising=False,
        )
        task = tg.create_task(asyncio.sleep(0))
        await task

    assert recorded


@pytest.mark.asyncio
async def test_on_task_done_notifies_completion_and_discards_awaited_by(monkeypatch) -> None:
    tg = CollectorTaskGroup()
    tg._parent_task = asyncio.current_task()
    tg._tasks = set()
    tg._errors = []
    tg._on_completed_fut = asyncio.get_running_loop().create_future()
    task = asyncio.create_task(asyncio.sleep(0))
    tg._tasks.add(task)

    discarded: list[tuple[asyncio.Task[None], asyncio.Task[None] | None]] = []
    monkeypatch.setattr(
        collector_module._futures_mod,
        "future_discard_from_awaited_by",
        lambda t, parent: discarded.append((t, parent)),
        raising=False,
    )

    await task
    tg._on_task_done(task)

    assert tg._on_completed_fut.done() is True
    assert discarded == [(task, tg._parent_task)]


@pytest.mark.asyncio
async def test_parent_cancel_requested_with_no_remaining_cancellation() -> None:
    tg = CollectorTaskGroup()
    tg._entered = True
    tg._exiting = True
    tg._loop = asyncio.get_running_loop()
    tg._parent_task = SimpleNamespace(uncancel=lambda: 0, cancelling=lambda: 0, cancel=lambda: None)
    tg._parent_cancel_requested = True
    tg._tasks = set()
    tg._errors = []

    assert await tg._aexit(asyncio.CancelledError, asyncio.CancelledError()) is None


@pytest.mark.asyncio
async def test_abort_only_cancels_pending_tasks() -> None:
    tg = CollectorTaskGroup()
    pending = asyncio.create_task(asyncio.sleep(0.01))
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    tg._tasks = {pending, done}

    tg._abort()

    assert pending.cancelled() or pending.cancelling()
    assert done.cancelled() is False


def test_is_base_error_recognizes_keyboard_interrupt() -> None:
    tg = CollectorTaskGroup()
    assert tg._is_base_error(KeyboardInterrupt()) is True


@pytest.mark.asyncio
async def test_base_error_is_raised_before_collected_errors() -> None:
    tg = CollectorTaskGroup()
    tg._entered = True
    tg._exiting = True
    tg._loop = asyncio.get_running_loop()
    tg._parent_task = asyncio.current_task()
    tg._tasks = set()
    tg._errors = [ValueError("boom")]
    tg._base_error = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        await tg._aexit(None, None)
