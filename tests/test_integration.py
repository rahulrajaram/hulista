"""Cross-package integration tests for hulista.

These tests verify that the 7 packages compose correctly:
  persistent-collections, sealed-typing, asyncio-actors,
  taskgroup-collect, fp-combinators, live-dispatch, with-update
"""
import asyncio
import sys
import os
from dataclasses import dataclass, field

import pytest

# ---------------------------------------------------------------------------
# Path setup — add each package to sys.path so imports work without install
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

for pkg_dir in [
    "persistent-collections",
    "sealed-typing",
    "asyncio-actors",
    "taskgroup-collect",
    "fp-combinators",
    "live-dispatch",
    "with-update",
]:
    path = os.path.join(_ROOT, pkg_dir)
    if path not in sys.path:
        sys.path.insert(0, path)


# ---------------------------------------------------------------------------
# 1. PersistentMap + sealed types
#    Store sealed-class instances in PersistentMap, pattern-match on retrieval.
# ---------------------------------------------------------------------------

class TestPersistentMapWithSealedTypes:
    """Sealed message types stored in a PersistentMap, retrieved and matched."""

    def setup_method(self):
        # Define sealed hierarchy inline (same module = allowed)
        from sealed_typing import sealed, assert_exhaustive

        @sealed
        class Event:
            pass

        class Click(Event):
            def __init__(self, x: int, y: int):
                self.x, self.y = x, y

        class KeyPress(Event):
            def __init__(self, key: str):
                self.key = key

        self.Event = Event
        self.Click = Click
        self.KeyPress = KeyPress

    def test_store_and_match(self):
        from persistent_collections import PersistentMap
        from sealed_typing import assert_exhaustive

        m = PersistentMap()
        m = m.set("e1", self.Click(10, 20))
        m = m.set("e2", self.KeyPress("Enter"))

        results = []
        for key in m:
            event = m[key]
            match event:
                case self.Click(x=x, y=y):
                    results.append(f"click({x},{y})")
                case self.KeyPress(key=k):
                    results.append(f"key({k})")
                case _:
                    assert_exhaustive(event, self.Click, self.KeyPress)

        assert sorted(results) == ["click(10,20)", "key(Enter)"]

    def test_persistent_map_preserves_sealed_instances(self):
        from persistent_collections import PersistentMap

        click = self.Click(5, 5)
        m1 = PersistentMap().set("c", click)
        m2 = m1.set("extra", "data")

        # Structural sharing — both maps reference the same Click object
        assert m1["c"] is m2["c"]
        assert isinstance(m2["c"], self.Click)


# ---------------------------------------------------------------------------
# 2. CollectorTaskGroup + actors
#    Spawn actors, fan out work via CollectorTaskGroup, collect results.
# ---------------------------------------------------------------------------

class TestCollectorTaskGroupWithActors:
    """Actors process messages; CollectorTaskGroup fans out work."""

    @pytest.mark.asyncio
    async def test_fan_out_with_actors(self):
        from asyncio_actors import Actor, ActorSystem
        from taskgroup_collect import CollectorTaskGroup

        class Doubler(Actor):
            async def on_message(self, n: int) -> int:
                return n * 2

        async with ActorSystem() as system:
            ref = await system.spawn(Doubler)

            # Fan out 5 ask() calls via CollectorTaskGroup
            tasks = []
            async with CollectorTaskGroup() as tg:
                for i in range(5):
                    tasks.append(tg.create_task(ref.ask(i)))

            results = sorted(t.result() for t in tasks)
            assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_collector_survives_actor_errors(self):
        from asyncio_actors import Actor, ActorSystem, SupervisionStrategy
        from taskgroup_collect import CollectorTaskGroup

        class FlakyWorker(Actor):
            async def on_message(self, n: int) -> int:
                if n == 3:
                    raise ValueError("bad input")
                return n * 10

            async def on_error(self, error):
                return SupervisionStrategy.RESTART

        async with ActorSystem() as system:
            ref = await system.spawn(FlakyWorker)

            tasks = []
            async with CollectorTaskGroup() as tg:
                for i in [1, 2, 4, 5]:
                    tasks.append(tg.create_task(ref.ask(i)))

            results = sorted(t.result() for t in tasks)
            assert results == [10, 20, 40, 50]


# ---------------------------------------------------------------------------
# 3. Live dispatch + sealed types
#    Register handlers for each sealed subclass, verify dispatch coverage.
# ---------------------------------------------------------------------------

class TestLiveDispatchWithSealedTypes:
    """Dispatcher handlers cover all sealed subclasses."""

    def test_exhaustive_dispatch(self):
        from sealed_typing import sealed, sealed_subclasses
        from live_dispatch import Dispatcher

        @sealed
        class Cmd:
            pass

        class Start(Cmd):
            pass

        class Stop(Cmd):
            pass

        dispatch = Dispatcher("cmd_handler")

        @dispatch.register
        def on_start(c: Start) -> str:
            return "started"

        @dispatch.register
        def on_stop(c: Stop) -> str:
            return "stopped"

        assert dispatch(Start()) == "started"
        assert dispatch(Stop()) == "stopped"

        # Verify dispatch covers all sealed subclasses
        registered_types = set()
        for h in dispatch.handlers():
            registered_types.update(h["types"].values())

        sealed_names = {cls.__name__ for cls in sealed_subclasses(Cmd)}
        assert sealed_names == {"Start", "Stop"}
        assert registered_types == {"Start", "Stop"}


# ---------------------------------------------------------------------------
# 4. PersistentMap + with-update
#    PersistentMap as a field in a frozen dataclass, update via | operator.
# ---------------------------------------------------------------------------

class TestPersistentMapWithUpdate:
    """Frozen dataclass holding a PersistentMap, updated via | operator."""

    def test_dataclass_with_persistent_map_field(self):
        from persistent_collections import PersistentMap
        from with_update import updatable

        @updatable
        @dataclass(frozen=True)
        class AppState:
            version: int = 1
            data: PersistentMap = field(default_factory=PersistentMap)

        s0 = AppState()
        s1 = s0 | {"data": s0.data.set("user", "alice")}
        s2 = s1 | {"version": 2, "data": s1.data.set("count", 42)}

        assert s0.version == 1
        assert len(s0.data) == 0

        assert s1.data["user"] == "alice"
        assert s1.version == 1

        assert s2.version == 2
        assert s2.data["user"] == "alice"
        assert s2.data["count"] == 42

    def test_with_update_method(self):
        from persistent_collections import PersistentMap
        from with_update import updatable

        @updatable
        @dataclass(frozen=True)
        class Settings:
            theme: str = "light"
            store: PersistentMap = field(default_factory=PersistentMap)

        s = Settings(store=PersistentMap(lang="en"))
        s2 = s.with_update(theme="dark")

        assert s.theme == "light"
        assert s2.theme == "dark"
        assert s2.store["lang"] == "en"


# ---------------------------------------------------------------------------
# 5. FP combinators + live dispatch
#    Build processing pipeline with pipe(), feed through dispatcher.
# ---------------------------------------------------------------------------

class TestFPCombinatorWithDispatch:
    """Pipe-based preprocessing feeds into a type dispatcher."""

    def test_pipe_into_dispatcher(self):
        from fp_combinators import pipe, pipeline
        from live_dispatch import Dispatcher

        dispatch = Dispatcher("formatter")

        @dispatch.register
        def fmt_int(x: int) -> str:
            return f"[{x:04d}]"

        @dispatch.register
        def fmt_str(x: str) -> str:
            return f'"{x}"'

        # Pipeline: parse string to int, then dispatch
        result = pipe("42", str.strip, int, dispatch)
        assert result == "[0042]"

        # Pipeline as reusable callable
        process = pipeline(str.strip, int, dispatch)
        assert process("  7  ") == "[0007]"

    def test_first_some_with_dispatch(self):
        from fp_combinators import first_some
        from live_dispatch import Dispatcher

        d1 = Dispatcher("d1")
        d2 = Dispatcher("d2")

        @d1.register
        def handle_int(x: int) -> str:
            return f"d1:{x}"

        @d2.register
        def handle_str(x: str) -> str:
            return f"d2:{x}"

        def try_d1(x):
            try:
                return d1(x)
            except TypeError:
                return None

        def try_d2(x):
            try:
                return d2(x)
            except TypeError:
                return None

        route = first_some(try_d1, try_d2)
        assert route(99) == "d1:99"
        assert route("hello") == "d2:hello"


# ---------------------------------------------------------------------------
# 6. Full pipeline
#    Sealed messages → actor inbox → pipe-based processing →
#    PersistentMap state accumulation → CollectorTaskGroup fan-out.
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """End-to-end: sealed types, actors, fp-combinators, persistent state, collector."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        from sealed_typing import sealed
        from persistent_collections import PersistentMap
        from asyncio_actors import Actor, ActorSystem
        from taskgroup_collect import CollectorTaskGroup
        from fp_combinators import pipe

        # -- Sealed message types --
        @sealed
        class Msg:
            pass

        class Increment(Msg):
            def __init__(self, key: str, amount: int):
                self.key = key
                self.amount = amount

        class GetState(Msg):
            pass

        # -- Actor that accumulates state in a PersistentMap --
        class Accumulator(Actor):
            async def on_start(self):
                self.state = PersistentMap()

            async def on_message(self, msg):
                match msg:
                    case Increment(key=k, amount=a):
                        current = self.state.get(k, 0)
                        self.state = self.state.set(k, current + a)
                        return self.state[k]
                    case GetState():
                        return dict(self.state.items())

        async with ActorSystem() as system:
            ref = await system.spawn(Accumulator)

            # Fan out increments via CollectorTaskGroup
            messages = [
                Increment("a", 1),
                Increment("b", 2),
                Increment("a", 3),
                Increment("b", 4),
            ]

            tasks = []
            async with CollectorTaskGroup() as tg:
                for msg in messages:
                    tasks.append(tg.create_task(ref.ask(msg)))

            # All tasks completed
            assert all(not t.cancelled() for t in tasks)

            # Verify accumulated state
            state = await ref.ask(GetState())

            # Use pipe to transform the state dict
            summary = pipe(
                state,
                lambda d: {k: v for k, v in d.items()},
                lambda d: sorted(d.items()),
                lambda items: ", ".join(f"{k}={v}" for k, v in items),
            )

            assert state["a"] == 4   # 1 + 3
            assert state["b"] == 6   # 2 + 4
            assert summary == "a=4, b=6"
