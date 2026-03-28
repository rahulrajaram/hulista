"""Tests for CollectorTaskGroup."""

import asyncio
from builtins import BaseExceptionGroup
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
        async with CollectorTaskGroup():
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


class TestChildFailureDoesNotInterruptBody:
    """A child failure does not unwind the active async-with body."""

    @staticmethod
    async def _run():
        marks = []

        async def fail():
            await asyncio.sleep(0.01)
            raise ValueError("boom")

        with pytest.raises(BaseExceptionGroup) as exc_info:
            async with CollectorTaskGroup() as tg:
                tg.create_task(fail())
                await asyncio.sleep(0.02)
                marks.append("body-continued")

        assert marks == ["body-continued"]
        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], ValueError)

    def test_child_failure_does_not_interrupt_body(self):
        asyncio.run(self._run())


class TestLateTaskCreationAfterFailure:
    """Tasks can still be created after an earlier child has failed."""

    @staticmethod
    async def _run():
        late_result = []

        async def fail():
            await asyncio.sleep(0.01)
            raise ValueError("boom")

        async def succeed():
            await asyncio.sleep(0.01)
            late_result.append("late-task-finished")

        with pytest.raises(BaseExceptionGroup) as exc_info:
            async with CollectorTaskGroup() as tg:
                tg.create_task(fail())
                await asyncio.sleep(0.02)
                tg.create_task(succeed())

        assert late_result == ["late-task-finished"]
        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], ValueError)

    def test_late_task_creation_after_failure(self):
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


class TestExternalCancellation:
    """External parent cancellation still propagates to children."""

    @staticmethod
    async def _run():
        child_cancelled = asyncio.Event()

        async def slow():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                child_cancelled.set()
                raise

        async def scenario():
            parent = asyncio.current_task()

            async def cancel_parent():
                await asyncio.sleep(0.01)
                parent.cancel()

            asyncio.create_task(cancel_parent())
            async with CollectorTaskGroup() as tg:
                tg.create_task(slow())
                await asyncio.sleep(10)

        with pytest.raises(asyncio.CancelledError):
            await scenario()

        assert child_cancelled.is_set()

    def test_external_cancellation(self):
        asyncio.run(self._run())


class TestCancellationAndErrorPrecedence:
    """A collected child error is raised before preserved parent cancellation."""

    @staticmethod
    async def _run():
        parent = asyncio.current_task()

        async def fail():
            await asyncio.sleep(0.01)
            raise ValueError("boom")

        async def cancel_parent():
            await asyncio.sleep(0.02)
            parent.cancel()

        asyncio.create_task(cancel_parent())

        with pytest.raises(BaseExceptionGroup) as exc_info:
            async with CollectorTaskGroup() as tg:
                tg.create_task(fail())
                await asyncio.sleep(0.03)

        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], ValueError)

        with pytest.raises(asyncio.CancelledError):
            await asyncio.sleep(0)

    def test_cancellation_and_error_precedence(self):
        asyncio.run(self._run())


class TestChildCancellation:
    """Child CancelledError is ignored rather than collected."""

    @staticmethod
    async def _run():
        async def cancel_self():
            raise asyncio.CancelledError()

        async with CollectorTaskGroup() as tg:
            tg.create_task(cancel_self())

    def test_child_cancellation_is_ignored(self):
        asyncio.run(self._run())


class TestBaseExceptionPrecedence:
    """SystemExit and KeyboardInterrupt win over ordinary aggregation."""

    @staticmethod
    async def _run():
        async def fail():
            await asyncio.sleep(0.01)
            raise ValueError("ordinary")

        async def exit_now():
            await asyncio.sleep(0.01)
            raise SystemExit("stop now")

        async with CollectorTaskGroup() as tg:
            tg.create_task(fail())
            tg.create_task(exit_now())

    def test_base_exception_precedence(self):
        with pytest.raises(SystemExit, match="stop now"):
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
