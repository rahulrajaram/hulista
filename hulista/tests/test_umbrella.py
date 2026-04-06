"""Tests for the hulista umbrella meta-package.

Verifies:
1. All re-exports are importable directly from ``hulista``
2. ``hulista.__version__`` is present and correct
3. Each re-exported name is the same object as the original (no wrapping)
4. A basic integration smoke test combining 2-3 packages
"""
from __future__ import annotations

from pathlib import Path
import tomllib
import pytest

import hulista


# ---------------------------------------------------------------------------
# 1. Version
# ---------------------------------------------------------------------------


def test_version_exists() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project_version = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert hasattr(hulista, "__version__")
    assert hulista.__version__ == project_version


def test_no_internal_distribution_dependencies() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text())["project"]
    dependencies = set(project.get("dependencies", []))
    internal = {
        "asyncio-actors>=0.1.0",
        "fp-combinators>=0.1.0",
        "live-dispatch>=0.1.0",
        "persistent-collections>=0.1.0",
        "sealed-typing>=0.1.0",
        "taskgroup-collect>=0.1.0",
        "with-update>=0.1.0",
    }
    assert dependencies.isdisjoint(internal)


# ---------------------------------------------------------------------------
# 2. All expected names are present in hulista namespace
# ---------------------------------------------------------------------------


EXPECTED_EXPORTS = [
    # persistent-collections
    "PersistentMap",
    "PersistentVector",
    "TransientMap",
    # fp-combinators
    "Result",
    "Ok",
    "Err",
    "pipe",
    "async_pipe",
    "async_try_pipe",
    # asyncio-actors
    "Actor",
    "ActorRef",
    "ActorSystem",
    # live-dispatch
    "Dispatcher",
    # sealed-typing
    "sealed",
    "sealed_subclasses",
    # taskgroup-collect
    "CollectorTaskGroup",
    # with-update
    "updatable",
    "with_update",
]


@pytest.mark.parametrize("name", EXPECTED_EXPORTS)
def test_name_exported(name: str) -> None:
    assert hasattr(hulista, name), f"hulista.{name} is missing"


def test_all_list_complete() -> None:
    """Every expected name is listed in __all__."""
    for name in EXPECTED_EXPORTS:
        assert name in hulista.__all__, f"{name!r} missing from hulista.__all__"


# ---------------------------------------------------------------------------
# 3. Identity checks — re-exported object is the original object
# ---------------------------------------------------------------------------


def test_persistent_map_identity() -> None:
    from persistent_collections import PersistentMap
    assert hulista.PersistentMap is PersistentMap


def test_persistent_vector_identity() -> None:
    from persistent_collections import PersistentVector
    assert hulista.PersistentVector is PersistentVector


def test_transient_map_identity() -> None:
    from persistent_collections import TransientMap
    assert hulista.TransientMap is TransientMap


def test_result_identity() -> None:
    from fp_combinators import Result
    assert hulista.Result is Result


def test_ok_identity() -> None:
    from fp_combinators import Ok
    assert hulista.Ok is Ok


def test_err_identity() -> None:
    from fp_combinators import Err
    assert hulista.Err is Err


def test_pipe_identity() -> None:
    from fp_combinators import pipe
    assert hulista.pipe is pipe


def test_async_pipe_identity() -> None:
    from fp_combinators import async_pipe
    assert hulista.async_pipe is async_pipe


def test_async_try_pipe_identity() -> None:
    from fp_combinators import async_try_pipe
    assert hulista.async_try_pipe is async_try_pipe


def test_actor_identity() -> None:
    from asyncio_actors import Actor
    assert hulista.Actor is Actor


def test_actor_ref_identity() -> None:
    from asyncio_actors import ActorRef
    assert hulista.ActorRef is ActorRef


def test_actor_system_identity() -> None:
    from asyncio_actors import ActorSystem
    assert hulista.ActorSystem is ActorSystem


def test_dispatcher_identity() -> None:
    from live_dispatch import Dispatcher
    assert hulista.Dispatcher is Dispatcher


def test_sealed_identity() -> None:
    from sealed_typing import sealed
    assert hulista.sealed is sealed


def test_sealed_subclasses_identity() -> None:
    from sealed_typing import sealed_subclasses
    assert hulista.sealed_subclasses is sealed_subclasses


def test_collector_task_group_identity() -> None:
    from taskgroup_collect import CollectorTaskGroup
    assert hulista.CollectorTaskGroup is CollectorTaskGroup


def test_updatable_identity() -> None:
    from with_update import updatable
    assert hulista.updatable is updatable


def test_with_update_identity() -> None:
    from with_update import with_update
    assert hulista.with_update is with_update


# ---------------------------------------------------------------------------
# 4. Integration smoke tests
# ---------------------------------------------------------------------------


def test_pipe_and_persistent_map() -> None:
    """pipe() transforming data stored in a PersistentMap."""
    m = hulista.PersistentMap()
    m = m.set("x", 3).set("y", 4)

    result = hulista.pipe(
        m,
        lambda pm: {k: v for k, v in pm.items()},
        lambda d: sorted(d.values()),
        sum,
    )
    assert result == 7


def test_ok_err_with_pipe() -> None:
    """Result/Ok/Err combined with pipe()."""
    def safe_div(pair: tuple) -> "hulista.Result[float, str]":
        a, b = pair
        if b == 0:
            return hulista.Err("division by zero")
        return hulista.Ok(a / b)

    ok_result = safe_div((10, 2))
    err_result = safe_div((5, 0))

    assert isinstance(ok_result, hulista.Ok)
    assert ok_result.value == 5.0

    assert isinstance(err_result, hulista.Err)
    assert err_result.error == "division by zero"


@pytest.mark.asyncio
async def test_actor_system_with_collector() -> None:
    """ActorSystem + CollectorTaskGroup smoke test."""

    class Squarer(hulista.Actor):
        async def on_message(self, n: int) -> int:
            return n * n

    async with hulista.ActorSystem() as system:
        ref = await system.spawn(Squarer)

        tasks = []
        async with hulista.CollectorTaskGroup() as tg:
            for i in range(1, 5):
                tasks.append(tg.create_task(ref.ask(i)))

    results = sorted(t.result() for t in tasks)
    assert results == [1, 4, 9, 16]


@hulista.sealed
class _Shape:
    pass


class _Circle(_Shape):
    def __init__(self, r: float) -> None:
        self.r = r


class _Square(_Shape):
    def __init__(self, side: float) -> None:
        self.side = side


def test_sealed_and_dispatcher() -> None:
    """sealed_subclasses + Dispatcher dispatch on sealed hierarchy.

    Note: The Dispatcher uses get_type_hints() to resolve annotations at
    registration time, which requires the annotated types to be available in
    the module globals.  Classes are therefore defined at module scope above.
    """
    import math

    d = hulista.Dispatcher("area")

    @d.register
    def circle_area(s: _Circle) -> float:
        return math.pi * s.r ** 2

    @d.register
    def square_area(s: _Square) -> float:
        return s.side ** 2

    assert hulista.sealed_subclasses(_Shape) == {_Circle, _Square}
    assert d(_Square(3.0)) == pytest.approx(9.0)
    assert d(_Circle(1.0)) == pytest.approx(3.14159, rel=1e-4)
