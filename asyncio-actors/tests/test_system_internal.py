from __future__ import annotations

import asyncio

import pytest

from asyncio_actors.actor import Actor
from asyncio_actors.system import ActorSystem


class _CrashOnStart(Actor):
    async def on_start(self) -> None:
        raise RuntimeError("boom")

    async def on_message(self, message: object) -> object:
        return message


@pytest.mark.asyncio
async def test_supervise_stops_when_system_shuts_down_during_backoff(monkeypatch) -> None:
    system = ActorSystem()
    system._running = True
    actor = _CrashOnStart()

    async def fake_sleep(delay: float) -> None:
        system._running = False

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await system._supervise(_CrashOnStart, (), {}, actor)
    assert system._actors == {}


@pytest.mark.asyncio
async def test_supervise_restart_without_registry_or_inbox_transfer() -> None:
    system = ActorSystem()
    system._running = True
    actor = _CrashOnStart()
    actor._inbox.close()
    actor.restart_policy.max_restarts = 1

    await system._supervise(_CrashOnStart, (), {}, actor)

    assert system._actors == {}
