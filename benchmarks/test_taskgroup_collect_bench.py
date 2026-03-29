from __future__ import annotations

import asyncio

from taskgroup_collect import CollectorTaskGroup


def test_taskgroup_successful_fanout(benchmark) -> None:
    runner = asyncio.Runner()

    async def once() -> list[int]:
        tasks = []
        async with CollectorTaskGroup() as tg:
            for i in range(8):
                tasks.append(tg.create_task(asyncio.sleep(0, result=i)))
        return [task.result() for task in tasks]

    try:
        result = benchmark(lambda: runner.run(once()))
    finally:
        runner.close()

    assert result == list(range(8))
