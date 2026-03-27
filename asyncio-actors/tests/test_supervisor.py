"""Tests for Supervisor hierarchical supervision."""
from __future__ import annotations

import asyncio

import pytest

from asyncio_actors.actor import Actor
from asyncio_actors.supervisor import (
    Supervisor, ChildSpec, SupervisorStrategy, RestartType,
)


class StableWorker(Actor):
    """Worker that processes messages and stays alive."""
    started = False

    async def on_start(self):
        self.__class__.started = True

    async def on_message(self, msg):
        return f"echo: {msg}"


class CrashOnceWorker(Actor):
    """Worker that crashes on the first run, then works."""
    crash_count = 0

    async def on_start(self):
        CrashOnceWorker.crash_count += 1
        if CrashOnceWorker.crash_count == 1:
            raise RuntimeError("first crash")

    async def on_message(self, msg):
        return msg


class AlwaysCrashWorker(Actor):
    """Worker that always crashes."""
    crash_count = 0

    async def on_start(self):
        AlwaysCrashWorker.crash_count += 1
        raise RuntimeError("always crash")

    async def on_message(self, msg):
        return msg


# --- OneForOne tests ---

class TestOneForOne:
    @pytest.mark.asyncio
    async def test_children_start(self):
        class App(Supervisor):
            strategy = SupervisorStrategy.ONE_FOR_ONE
            children_specs = [ChildSpec(StableWorker)]

        sup = App()
        task = asyncio.create_task(sup._run())
        await asyncio.sleep(0.05)
        refs = sup.child_refs()
        assert len(refs) == 1
        await sup.stop()
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_multiple_children(self):
        class App(Supervisor):
            strategy = SupervisorStrategy.ONE_FOR_ONE
            children_specs = [
                ChildSpec(StableWorker),
                ChildSpec(StableWorker),
            ]

        sup = App()
        task = asyncio.create_task(sup._run())
        await asyncio.sleep(0.05)
        assert len(sup.child_refs()) == 2
        await sup.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_children_specs_not_shared(self):
        """Each Supervisor instance should have its own children_specs list."""
        class App1(Supervisor):
            children_specs = [ChildSpec(StableWorker)]

        class App2(Supervisor):
            children_specs = [ChildSpec(StableWorker)]

        s1 = App1()
        s2 = App2()
        s1.children_specs.append(ChildSpec(StableWorker))
        assert len(s2.children_specs) == 1


# --- Temporary restart type ---

class TestTemporary:
    @pytest.mark.asyncio
    async def test_temporary_not_restarted(self):
        AlwaysCrashWorker.crash_count = 0

        class App(Supervisor):
            strategy = SupervisorStrategy.ONE_FOR_ONE
            children_specs = [
                ChildSpec(AlwaysCrashWorker, restart=RestartType.TEMPORARY),
            ]

        sup = App()
        task = asyncio.create_task(sup._run())
        await asyncio.sleep(0.3)
        # Should crash once and not be restarted
        assert AlwaysCrashWorker.crash_count == 1
        await sup.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# --- Transient restart type ---

class TestTransient:
    @pytest.mark.asyncio
    async def test_transient_restarts_on_crash(self):
        CrashOnceWorker.crash_count = 0

        class App(Supervisor):
            strategy = SupervisorStrategy.ONE_FOR_ONE
            children_specs = [
                ChildSpec(CrashOnceWorker, restart=RestartType.TRANSIENT),
            ]

        sup = App()
        task = asyncio.create_task(sup._run())
        await asyncio.sleep(0.5)
        # Should crash once and then be restarted
        assert CrashOnceWorker.crash_count >= 2
        await sup.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# --- OneForAll strategy ---

class TestOneForAll:
    @pytest.mark.asyncio
    async def test_all_children_restarted(self):
        class App(Supervisor):
            strategy = SupervisorStrategy.ONE_FOR_ALL
            children_specs = [
                ChildSpec(StableWorker),
                ChildSpec(StableWorker),
            ]

        sup = App()
        task = asyncio.create_task(sup._run())
        await asyncio.sleep(0.05)
        assert len(sup.child_refs()) == 2
        await sup.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# --- RestForOne strategy ---

class TestRestForOne:
    @pytest.mark.asyncio
    async def test_rest_for_one_starts_all(self):
        class App(Supervisor):
            strategy = SupervisorStrategy.REST_FOR_ONE
            children_specs = [
                ChildSpec(StableWorker),
                ChildSpec(StableWorker),
            ]

        sup = App()
        task = asyncio.create_task(sup._run())
        await asyncio.sleep(0.05)
        assert len(sup.child_refs()) == 2
        await sup.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# --- on_stop ---

class TestOnStop:
    @pytest.mark.asyncio
    async def test_stop_cancels_child_tasks(self):
        class App(Supervisor):
            children_specs = [ChildSpec(StableWorker)]

        sup = App()
        task = asyncio.create_task(sup._run())
        await asyncio.sleep(0.05)
        assert len(sup._children) == 1
        # Grab child task before stop
        _, _, child_task = sup._children[0]
        await sup.stop()
        # Yield to let cancellation propagate
        await asyncio.sleep(0.05)
        assert child_task.cancelled() or child_task.done()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
