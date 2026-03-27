"""Tests for CollectorTaskGroup."""

import asyncio
import pytest

from taskgroup_collect import CollectorTaskGroup


@pytest.fixture
def run(event_loop_policy):
    """Run an async function to completion."""
    def _run(coro):
        return asyncio.run(coro)
    return _run


# --- Core behaviour ---

class TestAllTasksComplete:
    """The defining feature: sibling tasks are NOT cancelled on error."""

    @staticmethod
    async def _run():
        results = {}

        async def succeed(key, val, delay=0.01):
            await asyncio.sleep(delay)
            results[key] = val

        async def fail():
            await asyncio.sleep(0.01)
            raise ValueError("boom")

        with pytest.raises(BaseExceptionGroup) as exc_info:
            async with CollectorTaskGroup() as tg:
                tg.create_task(succeed("a", 1))
                tg.create_task(fail())
                tg.create_task(succeed("b", 2))

        # ALL successful tasks completed, not just the ones before the failure.
        assert results == {"a": 1, "b": 2}
        # The exception group contains the error.
        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], ValueError)

    def test_all_tasks_complete(self):
        asyncio.run(self._run())


class TestMultipleErrors:
    """Multiple tasks can fail; all errors are collected."""

    @staticmethod
    async def _run():
        async def fail_with(exc):
            await asyncio.sleep(0.01)
            raise exc

        with pytest.raises(BaseExceptionGroup) as exc_info:
            async with CollectorTaskGroup() as tg:
                tg.create_task(fail_with(ValueError("one")))
                tg.create_task(fail_with(TypeError("two")))
                tg.create_task(fail_with(RuntimeError("three")))

        errors = exc_info.value.exceptions
        assert len(errors) == 3
        types = {type(e) for e in errors}
        assert types == {ValueError, TypeError, RuntimeError}

    def test_multiple_errors(self):
        asyncio.run(self._run())


class TestNoErrors:
    """When all tasks succeed, no exception is raised."""

    @staticmethod
    async def _run():
        results = []

        async def append(val):
            await asyncio.sleep(0.01)
            results.append(val)

        async with CollectorTaskGroup() as tg:
            tg.create_task(append(1))
            tg.create_task(append(2))
            tg.create_task(append(3))

        assert sorted(results) == [1, 2, 3]

    def test_no_errors(self):
        asyncio.run(self._run())


class TestResultAccess:
    """Individual task results are accessible after completion."""

    @staticmethod
    async def _run():
        async def compute(x):
            await asyncio.sleep(0.01)
            return x * 2

        async def fail():
            await asyncio.sleep(0.01)
            raise ValueError("oops")

        with pytest.raises(BaseExceptionGroup):
            async with CollectorTaskGroup() as tg:
                t1 = tg.create_task(compute(5))
                t2 = tg.create_task(fail())
                t3 = tg.create_task(compute(10))

        # Successful tasks have results.
        assert t1.result() == 10
        assert t3.result() == 20
        # Failed task has exception.
        assert isinstance(t2.exception(), ValueError)

    def test_result_access(self):
        asyncio.run(self._run())


class TestEmptyGroup:
    """An empty group completes without error."""

    @staticmethod
    async def _run():
        async with CollectorTaskGroup() as tg:
            pass  # No tasks

    def test_empty_group(self):
        asyncio.run(self._run())


class TestExceptionInBody:
    """An exception in the async-with body still cancels children."""

    @staticmethod
    async def _run():
        cancelled = False

        async def slow():
            nonlocal cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled = True
                raise

        with pytest.raises(BaseExceptionGroup) as exc_info:
            async with CollectorTaskGroup() as tg:
                tg.create_task(slow())
                await asyncio.sleep(0)  # Yield so the task starts
                raise RuntimeError("body error")

        # The body error triggers _abort, which cancels children.
        assert cancelled
        assert any(isinstance(e, RuntimeError) for e in exc_info.value.exceptions)

    def test_exception_in_body(self):
        asyncio.run(self._run())


class TestRepr:
    """Repr shows useful state."""

    @staticmethod
    async def _run():
        async with CollectorTaskGroup() as tg:
            assert 'entered' in repr(tg)

    def test_repr(self):
        asyncio.run(self._run())


class TestCreateTaskAfterExit:
    """create_task raises after the group has exited."""

    @staticmethod
    async def _run():
        async with CollectorTaskGroup() as tg:
            pass

        with pytest.raises(RuntimeError, match="(has not been entered|is finished)"):
            tg.create_task(asyncio.sleep(0))

    def test_create_task_after_exit(self):
        asyncio.run(self._run())


class TestDoubleEnter:
    """Entering twice raises RuntimeError."""

    @staticmethod
    async def _run():
        tg = CollectorTaskGroup()
        async with tg:
            with pytest.raises(RuntimeError, match="already been entered"):
                async with tg:
                    pass

    def test_double_enter(self):
        asyncio.run(self._run())


# --- Comparison with stdlib TaskGroup ---

class TestStdlibCancelsOnFirstError:
    """Demonstrate that stdlib TaskGroup DOES cancel siblings (for contrast)."""

    @staticmethod
    async def _run():
        completed = set()

        async def track(key):
            try:
                await asyncio.sleep(0.1)
                completed.add(key)
            except asyncio.CancelledError:
                pass

        async def fail_fast():
            await asyncio.sleep(0.01)
            raise ValueError("fast fail")

        with pytest.raises(BaseExceptionGroup):
            async with asyncio.TaskGroup() as tg:
                tg.create_task(track("a"))
                tg.create_task(fail_fast())
                tg.create_task(track("b"))

        # Stdlib: siblings got cancelled, so they did NOT complete.
        assert completed == set()

    def test_stdlib_cancels(self):
        asyncio.run(self._run())


class TestCollectorDoesNotCancel:
    """CollectorTaskGroup does NOT cancel siblings (same scenario)."""

    @staticmethod
    async def _run():
        completed = set()

        async def track(key):
            await asyncio.sleep(0.05)
            completed.add(key)

        async def fail_fast():
            await asyncio.sleep(0.01)
            raise ValueError("fast fail")

        with pytest.raises(BaseExceptionGroup):
            async with CollectorTaskGroup() as tg:
                tg.create_task(track("a"))
                tg.create_task(fail_fast())
                tg.create_task(track("b"))

        # Collector: siblings completed despite the error.
        assert completed == {"a", "b"}

    def test_collector_does_not_cancel(self):
        asyncio.run(self._run())
