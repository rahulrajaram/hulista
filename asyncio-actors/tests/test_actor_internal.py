from __future__ import annotations

import asyncio

import pytest

from asyncio_actors.actor import Actor
from asyncio_actors.supervision import SupervisionStrategy
from asyncio_actors.system import ActorSystem
import asyncio_actors.actor as actor_module


@pytest.mark.asyncio
async def test_base_actor_default_hooks() -> None:
    actor = Actor()
    await actor.on_start()
    with pytest.raises(NotImplementedError):
        await actor.on_message("boom")
    assert await actor.on_error(RuntimeError("x")) == SupervisionStrategy.RESTART
    await actor.reply("ignored")
    await actor.on_stop()


@pytest.mark.asyncio
async def test_stop_from_inside_actor_does_not_cancel_current_task() -> None:
    stopped = asyncio.Event()

    class SelfStoppingActor(Actor):
        async def on_message(self, message: str) -> str | None:
            if message == "stop":
                await self.stop()
                stopped.set()
            return message

    actor = SelfStoppingActor()
    task = asyncio.create_task(actor._run())
    await actor._inbox.put("stop")
    await asyncio.wait_for(stopped.wait(), timeout=1.0)
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_system_supervision_stops_after_restart_limit(monkeypatch) -> None:
    class CrashActor(Actor):
        async def on_start(self) -> None:
            raise RuntimeError("boom")

        async def on_message(self, message: object) -> object:
            return message

    async with ActorSystem() as system:
        actor = CrashActor()
        actor.restart_policy.max_restarts = 0
        await system._supervise(CrashActor, (), {}, actor)
        assert system._actors == {}


@pytest.mark.asyncio
async def test_actor_run_continues_after_timeout(monkeypatch) -> None:
    class IdleActor(Actor):
        async def on_message(self, message: object) -> object:
            return message

    actor = IdleActor()
    calls = 0

    async def fake_wait_for(awaitable, timeout: float):
        nonlocal calls
        calls += 1
        awaitable.close()
        if calls == 1:
            raise asyncio.TimeoutError
        raise RuntimeError("Inbox is closed and empty")

    monkeypatch.setattr(actor_module.asyncio, "wait_for", fake_wait_for)

    await actor._run()
    assert calls == 2


@pytest.mark.asyncio
async def test_actor_task_cancellation_propagates_when_running() -> None:
    started = asyncio.Event()

    class SlowActor(Actor):
        async def on_message(self, message: object) -> None:
            started.set()
            await asyncio.sleep(10)

    actor = SlowActor()
    task = asyncio.create_task(actor._run())
    await actor._inbox.put("work")
    await asyncio.wait_for(started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
