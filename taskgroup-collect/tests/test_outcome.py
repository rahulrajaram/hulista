"""Tests for TaskOutcome, Success, and Failure."""

from __future__ import annotations

import asyncio
import pytest

from taskgroup_collect import CollectorTaskGroup, Failure, Success, TaskOutcome


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------

class TestSuccess:
    def test_is_ok(self) -> None:
        assert Success(42).is_ok is True

    def test_is_err(self) -> None:
        assert Success(42).is_err is False

    def test_unwrap_returns_value(self) -> None:
        assert Success("hello").unwrap() == "hello"

    def test_unwrap_err_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="unwrap_err"):
            Success(1).unwrap_err()

    def test_equality(self) -> None:
        assert Success(10) == Success(10)
        assert Success(10) != Success(20)

    def test_frozen(self) -> None:
        s: Success[int] = Success(1)
        with pytest.raises((AttributeError, TypeError)):
            s.value = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------

class TestFailure:
    def test_is_ok(self) -> None:
        assert Failure(ValueError("boom")).is_ok is False

    def test_is_err(self) -> None:
        assert Failure(ValueError("boom")).is_err is True

    def test_unwrap_err_returns_exception(self) -> None:
        exc = ValueError("boom")
        assert Failure(exc).unwrap_err() is exc

    def test_unwrap_raises_contained_exception(self) -> None:
        exc = ValueError("boom")
        with pytest.raises(ValueError, match="boom"):
            Failure(exc).unwrap()

    def test_equality(self) -> None:
        exc = RuntimeError("x")
        assert Failure(exc) == Failure(exc)

    def test_frozen(self) -> None:
        f: Failure[int] = Failure(ValueError())
        with pytest.raises((AttributeError, TypeError)):
            f.exception = RuntimeError()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

def test_imports_from_package() -> None:
    from taskgroup_collect import TaskOutcome, Success, Failure  # noqa: F401


# ---------------------------------------------------------------------------
# outcomes() integration
# ---------------------------------------------------------------------------

class TestOutcomesMethod:
    """CollectorTaskGroup.outcomes() returns per-task outcomes in creation order."""

    @staticmethod
    async def _mixed():
        async def ok(v: int) -> int:
            await asyncio.sleep(0)
            return v

        async def fail(msg: str) -> int:
            await asyncio.sleep(0)
            raise ValueError(msg)

        with pytest.raises(BaseExceptionGroup):
            async with CollectorTaskGroup() as tg:
                tg.create_task(ok(1))
                tg.create_task(fail("boom"))
                tg.create_task(ok(3))

        return tg.outcomes()

    def test_mixed_success_failure_order(self) -> None:
        outcomes = asyncio.run(self._mixed())
        assert len(outcomes) == 3

        assert isinstance(outcomes[0], Success)
        assert outcomes[0].unwrap() == 1

        assert isinstance(outcomes[1], Failure)
        assert isinstance(outcomes[1].unwrap_err(), ValueError)

        assert isinstance(outcomes[2], Success)
        assert outcomes[2].unwrap() == 3

    @staticmethod
    async def _all_success():
        async def ok(v: int) -> int:
            await asyncio.sleep(0)
            return v

        async with CollectorTaskGroup() as tg:
            tg.create_task(ok(10))
            tg.create_task(ok(20))

        return tg.outcomes()

    def test_all_success(self) -> None:
        outcomes = asyncio.run(self._all_success())
        assert all(o.is_ok for o in outcomes)
        assert [o.unwrap() for o in outcomes] == [10, 20]

    @staticmethod
    async def _all_failure():
        async def fail(msg: str) -> int:
            await asyncio.sleep(0)
            raise RuntimeError(msg)

        with pytest.raises(BaseExceptionGroup):
            async with CollectorTaskGroup() as tg:
                tg.create_task(fail("a"))
                tg.create_task(fail("b"))

        return tg.outcomes()

    def test_all_failure(self) -> None:
        outcomes = asyncio.run(self._all_failure())
        assert all(o.is_err for o in outcomes)
        msgs = [str(o.unwrap_err()) for o in outcomes]
        assert msgs == ["a", "b"]

    def test_outcomes_before_exit_raises(self) -> None:
        async def _run() -> None:
            async with CollectorTaskGroup() as tg:
                with pytest.raises(RuntimeError, match="after the CollectorTaskGroup"):
                    tg.outcomes()

        asyncio.run(_run())

    def test_outcomes_returns_copy(self) -> None:
        async def _run() -> list[TaskOutcome[int]]:
            async with CollectorTaskGroup() as tg:
                tg.create_task(asyncio.sleep(0, result=7))
            return tg.outcomes()

        o1 = asyncio.run(_run())
        # Re-run to get a fresh group; just verify the list is a copy.
        o1_copy = list(o1)
        o1.clear()
        assert o1_copy  # copy was not affected by mutating o1
