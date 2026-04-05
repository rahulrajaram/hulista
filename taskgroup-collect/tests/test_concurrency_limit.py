"""Tests for CollectorTaskGroup's optional concurrency limit."""

from __future__ import annotations

import asyncio
import pytest

from taskgroup_collect import CollectorTaskGroup


class TestConcurrencyLimit:
    """limit= caps simultaneous active coroutines."""

    @staticmethod
    async def _measure_peak(limit: int, n_tasks: int) -> int:
        """Return the peak number of tasks running at the same time."""
        active = 0
        peak = 0
        _gate = asyncio.Event()

        async def worker() -> None:
            nonlocal active, peak
            active += 1
            if active > peak:
                peak = active
            # Wait a beat so siblings have time to start (and hit the sem).
            await asyncio.sleep(0.02)
            active -= 1

        async with CollectorTaskGroup(limit=limit) as tg:
            for _ in range(n_tasks):
                tg.create_task(worker())

        return peak

    def test_limit_1_serialises_tasks(self) -> None:
        peak = asyncio.run(self._measure_peak(limit=1, n_tasks=4))
        assert peak == 1

    def test_limit_2_allows_two_concurrent(self) -> None:
        peak = asyncio.run(self._measure_peak(limit=2, n_tasks=6))
        assert peak <= 2

    def test_limit_equal_to_task_count(self) -> None:
        peak = asyncio.run(self._measure_peak(limit=4, n_tasks=4))
        # All 4 may run together; peak should be exactly 4.
        assert peak == 4

    def test_no_limit_allows_all_concurrent(self) -> None:
        # limit=None (default) should not restrict concurrency.
        peak = asyncio.run(self._measure_peak(limit=10, n_tasks=10))
        assert peak == 10

    def test_invalid_limit_raises(self) -> None:
        with pytest.raises(ValueError, match="limit must be >= 1"):
            CollectorTaskGroup(limit=0)

        with pytest.raises(ValueError, match="limit must be >= 1"):
            CollectorTaskGroup(limit=-3)

    def test_limit_none_is_backward_compatible(self) -> None:
        """CollectorTaskGroup() with no args must still work."""
        async def _run() -> list[int]:
            results: list[int] = []

            async def append(v: int) -> None:
                await asyncio.sleep(0)
                results.append(v)

            async with CollectorTaskGroup() as tg:
                for i in range(5):
                    tg.create_task(append(i))

            return results

        results = asyncio.run(_run())
        assert sorted(results) == [0, 1, 2, 3, 4]

    def test_limit_with_errors_still_collects_all(self) -> None:
        """A limited group still collects all errors, not just the first."""

        async def _run() -> None:
            async def fail(msg: str) -> None:
                await asyncio.sleep(0.01)
                raise ValueError(msg)

            with pytest.raises(BaseExceptionGroup) as exc_info:
                async with CollectorTaskGroup(limit=2) as tg:
                    tg.create_task(fail("a"))
                    tg.create_task(fail("b"))
                    tg.create_task(fail("c"))

            assert len(exc_info.value.exceptions) == 3

        asyncio.run(_run())

    def test_limit_repr_shows_limit(self) -> None:
        async def _run() -> None:
            async with CollectorTaskGroup(limit=3) as tg:
                r = repr(tg)
            assert "limit=3" in r

        asyncio.run(_run())

    def test_limit_outcomes_in_creation_order(self) -> None:
        """outcomes() must preserve creation order even with a concurrency cap."""

        async def _run() -> None:
            async def ok(v: int) -> int:
                await asyncio.sleep(0.01)
                return v

            async def fail() -> int:
                await asyncio.sleep(0.01)
                raise RuntimeError("x")

            with pytest.raises(BaseExceptionGroup):
                async with CollectorTaskGroup(limit=1) as tg:
                    tg.create_task(ok(1))
                    tg.create_task(fail())
                    tg.create_task(ok(3))

            outcomes = tg.outcomes()
            assert outcomes[0].is_ok and outcomes[0].unwrap() == 1
            assert outcomes[1].is_err
            assert outcomes[2].is_ok and outcomes[2].unwrap() == 3

        asyncio.run(_run())
