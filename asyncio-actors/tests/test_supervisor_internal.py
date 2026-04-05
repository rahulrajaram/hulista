from __future__ import annotations


import pytest

from asyncio_actors.actor import Actor
from asyncio_actors.supervisor import ChildSpec, RestartType, Supervisor, SupervisorStrategy


class _Worker(Actor):
    async def on_message(self, message: object) -> object:
        return message


class _Supervisor(Supervisor):
    strategy = SupervisorStrategy.ONE_FOR_ONE
    children_specs = [ChildSpec(_Worker)]


class _FakeTask:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


@pytest.mark.asyncio
async def test_handle_child_exit_skips_temporary_and_transient_normal(monkeypatch) -> None:
    supervisor = _Supervisor()
    actor = _Worker()
    restarted: list[tuple[ChildSpec, Actor]] = []

    async def restart_child(spec: ChildSpec, old_actor: Actor) -> None:
        restarted.append((spec, old_actor))

    monkeypatch.setattr(supervisor, "_restart_child", restart_child)

    await supervisor._handle_child_exit(
        ChildSpec(_Worker, restart=RestartType.TEMPORARY),
        actor,
        normal=False,
    )
    await supervisor._handle_child_exit(
        ChildSpec(_Worker, restart=RestartType.TRANSIENT),
        actor,
        normal=True,
    )

    assert restarted == []


@pytest.mark.asyncio
async def test_restart_all_stops_and_restarts_children(monkeypatch) -> None:
    supervisor = _Supervisor()
    first = _Worker()
    second = _Worker()
    first_task = _FakeTask()
    second_task = _FakeTask()
    supervisor._children = [
        (ChildSpec(_Worker), first, first_task),
        (ChildSpec(_Worker), second, second_task),
    ]

    restarted: list[Actor] = []

    async def start_child(spec: ChildSpec, *, previous_actor: Actor | None = None, preserve_inbox: bool = False) -> Actor:
        assert preserve_inbox is False
        assert previous_actor is not None
        restarted.append(previous_actor)
        return _Worker()

    monkeypatch.setattr(supervisor, "_start_child", start_child)

    await supervisor._restart_all()

    assert first_task.cancelled is True
    assert second_task.cancelled is True
    assert restarted == [first, second]


@pytest.mark.asyncio
async def test_restart_rest_restarts_from_failed_spec(monkeypatch) -> None:
    spec1 = ChildSpec(_Worker)
    spec2 = ChildSpec(_Worker)
    spec3 = ChildSpec(_Worker)
    supervisor = _Supervisor()
    actor1 = _Worker()
    actor2 = _Worker()
    actor3 = _Worker()
    task1 = _FakeTask()
    task2 = _FakeTask()
    task3 = _FakeTask()
    supervisor._children = [
        (spec1, actor1, task1),
        (spec2, actor2, task2),
        (spec3, actor3, task3),
    ]

    restarted: list[tuple[Actor, bool]] = []

    async def start_child(spec: ChildSpec, *, previous_actor: Actor | None = None, preserve_inbox: bool = False) -> Actor:
        assert previous_actor is not None
        restarted.append((previous_actor, preserve_inbox))
        return _Worker()

    monkeypatch.setattr(supervisor, "_start_child", start_child)

    await supervisor._restart_rest(spec2)

    assert task1.cancelled is False
    assert task2.cancelled is True
    assert task3.cancelled is True
    assert restarted == [(actor2, False), (actor3, False)]


@pytest.mark.asyncio
async def test_restart_rest_ignores_unknown_spec() -> None:
    supervisor = _Supervisor()
    await supervisor._restart_rest(ChildSpec(_Worker))


@pytest.mark.asyncio
async def test_supervisor_on_message_returns_none() -> None:
    supervisor = _Supervisor()
    assert await supervisor.on_message("ignored") is None
