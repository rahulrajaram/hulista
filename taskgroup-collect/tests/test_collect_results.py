"""Tests for collect_results() convenience function."""

from __future__ import annotations

import asyncio

from taskgroup_collect import Failure, Success, collect_results


class TestCollectResults:
    """collect_results() runs all coroutines and returns outcomes."""

    @staticmethod
    async def _all_succeed() -> None:
        async def ok(v: int) -> int:
            await asyncio.sleep(0)
            return v

        outcomes = await collect_results([ok(1), ok(2), ok(3)])

        assert len(outcomes) == 3
        assert all(isinstance(o, Success) for o in outcomes)
        assert [o.unwrap() for o in outcomes] == [1, 2, 3]

    def test_all_succeed_returns_success_list(self) -> None:
        asyncio.run(self._all_succeed())

    @staticmethod
    async def _failure_captured() -> None:
        async def ok(v: int) -> int:
            await asyncio.sleep(0)
            return v

        async def fail(msg: str) -> int:
            await asyncio.sleep(0)
            raise ValueError(msg)

        outcomes = await collect_results([ok(1), fail("boom"), ok(3)])

        assert len(outcomes) == 3
        assert isinstance(outcomes[0], Success)
        assert outcomes[0].unwrap() == 1

        assert isinstance(outcomes[1], Failure)
        assert isinstance(outcomes[1].unwrap_err(), ValueError)
        assert str(outcomes[1].unwrap_err()) == "boom"

        assert isinstance(outcomes[2], Success)
        assert outcomes[2].unwrap() == 3

    def test_failure_captured_as_failure_outcome(self) -> None:
        asyncio.run(self._failure_captured())

    @staticmethod
    async def _preserves_order() -> None:
        """Results must appear in the same order as the input coroutines."""
        order: list[int] = []

        async def worker(idx: int, delay: float) -> int:
            await asyncio.sleep(delay)
            order.append(idx)
            return idx

        # Use varying delays so completion order differs from creation order.
        outcomes = await collect_results([
            worker(0, 0.03),
            worker(1, 0.01),
            worker(2, 0.02),
        ])

        # Completion order is 1, 2, 0 — but outcome order must match creation.
        assert [o.unwrap() for o in outcomes] == [0, 1, 2]
        # Sanity: tasks did complete in a different order.
        assert order == [1, 2, 0]

    def test_preserves_creation_order(self) -> None:
        asyncio.run(self._preserves_order())

    @staticmethod
    async def _empty() -> None:
        outcomes = await collect_results([])
        assert outcomes == []

    def test_empty_returns_empty_list(self) -> None:
        asyncio.run(self._empty())

    @staticmethod
    async def _limit_bounds_concurrency(limit: int) -> int:
        """Return the peak concurrency observed."""
        active = 0
        peak = 0

        async def worker() -> None:
            nonlocal active, peak
            active += 1
            if active > peak:
                peak = active
            await asyncio.sleep(0.02)
            active -= 1

        await collect_results([worker() for _ in range(6)], limit=limit)
        return peak

    def test_limit_bounds_concurrency(self) -> None:
        peak = asyncio.run(self._limit_bounds_concurrency(limit=2))
        assert peak <= 2

    @staticmethod
    async def _all_fail() -> None:
        async def fail(msg: str) -> int:
            await asyncio.sleep(0)
            raise RuntimeError(msg)

        outcomes = await collect_results([fail("a"), fail("b"), fail("c")])

        assert len(outcomes) == 3
        assert all(isinstance(o, Failure) for o in outcomes)
        msgs = [str(o.unwrap_err()) for o in outcomes]
        assert msgs == ["a", "b", "c"]

    def test_all_fail_returns_all_failures(self) -> None:
        asyncio.run(self._all_fail())

    @staticmethod
    async def _single_coro_success() -> None:
        async def ok() -> str:
            await asyncio.sleep(0)
            return "only"

        outcomes = await collect_results([ok()])
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], Success)
        assert outcomes[0].unwrap() == "only"

    @staticmethod
    async def _single_coro_failure() -> None:
        async def fail() -> str:
            await asyncio.sleep(0)
            raise TypeError("single failure")

        outcomes = await collect_results([fail()])
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], Failure)
        assert isinstance(outcomes[0].unwrap_err(), TypeError)

    def test_single_coro(self) -> None:
        asyncio.run(self._single_coro_success())
        asyncio.run(self._single_coro_failure())

    def test_does_not_raise_base_exception_group(self) -> None:
        """collect_results must never propagate BaseExceptionGroup to the caller."""

        async def _run() -> None:
            async def fail(msg: str) -> int:
                raise ValueError(msg)

            # This must not raise — all failures are captured in outcomes.
            outcomes = await collect_results([fail("x"), fail("y")])
            assert all(o.is_err for o in outcomes)

        asyncio.run(_run())

    def test_limit_none_runs_all_concurrently(self) -> None:
        """No limit means all coroutines may run simultaneously."""

        async def _run() -> None:
            active = 0
            peak = 0

            async def worker() -> None:
                nonlocal active, peak
                active += 1
                if active > peak:
                    peak = active
                await asyncio.sleep(0.02)
                active -= 1

            await collect_results([worker() for _ in range(5)], limit=None)
            assert peak == 5

        asyncio.run(_run())
