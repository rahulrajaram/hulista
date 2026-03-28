from __future__ import annotations

import asyncio

from asyncio_actors import Actor, Inbox, OverflowPolicy


class _NoopActor(Actor):
    async def on_message(self, message: int) -> None:
        return None


def test_asyncio_actorref_tell_roundtrip(benchmark) -> None:
    actor = _NoopActor()
    ref = actor.ref()
    runner = asyncio.Runner()

    async def once() -> int:
        await ref.send(1)
        return await actor._inbox.get()

    try:
        result = benchmark(lambda: runner.run(once()))
    finally:
        runner.close()

    assert result == 1


def test_asyncio_inbox_selective_receive(benchmark) -> None:
    runner = asyncio.Runner()

    async def once() -> str:
        inbox: Inbox[object] = Inbox(maxsize=4, policy=OverflowPolicy.BLOCK)
        await inbox.put(1)
        await inbox.put("needle")
        await inbox.put(2)
        return await inbox.receive(str)

    try:
        result = benchmark(lambda: runner.run(once()))
    finally:
        runner.close()

    assert result == "needle"
