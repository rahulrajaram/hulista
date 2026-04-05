"""Tests for freeze() and thaw() recursive conversion helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from persistent_collections import PersistentMap, PersistentVector, freeze, thaw


# ---------------------------------------------------------------------------
# TestFreeze
# ---------------------------------------------------------------------------


class TestFreeze:
    def test_dict_to_persistent_map(self):
        result = freeze({"a": 1, "b": 2})
        assert isinstance(result, PersistentMap)
        assert result["a"] == 1
        assert result["b"] == 2

    def test_nested_dict(self):
        result = freeze({"outer": {"inner": 42}})
        assert isinstance(result, PersistentMap)
        assert isinstance(result["outer"], PersistentMap)
        assert result["outer"]["inner"] == 42

    def test_list_to_persistent_vector(self):
        result = freeze([1, 2, 3])
        assert isinstance(result, PersistentVector)
        assert result[0] == 1
        assert result[1] == 2
        assert result[2] == 3

    def test_tuple_to_persistent_vector(self):
        result = freeze((10, 20, 30))
        assert isinstance(result, PersistentVector)
        assert result[0] == 10
        assert result[1] == 20
        assert result[2] == 30

    def test_nested_dict_with_lists(self):
        data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
        result = freeze(data)
        assert isinstance(result, PersistentMap)
        assert isinstance(result["users"], PersistentVector)
        assert isinstance(result["users"][0], PersistentMap)
        assert result["users"][0]["name"] == "Alice"
        assert isinstance(result["users"][1], PersistentMap)
        assert result["users"][1]["name"] == "Bob"

    def test_primitives_pass_through(self):
        assert freeze(42) == 42
        assert freeze("hello") == "hello"
        assert freeze(3.14) == 3.14
        assert freeze(None) is None
        assert freeze(True) is True
        assert freeze(False) is False

    def test_already_persistent_map_passes_through(self):
        pm = PersistentMap(x=1)
        result = freeze(pm)
        assert result is pm

    def test_already_persistent_vector_passes_through(self):
        pv = PersistentVector()
        pv = pv.append(1).append(2)
        result = freeze(pv)
        assert result is pv

    def test_empty_dict(self):
        result = freeze({})
        assert isinstance(result, PersistentMap)
        assert len(result) == 0

    def test_empty_list(self):
        result = freeze([])
        assert isinstance(result, PersistentVector)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# TestThaw
# ---------------------------------------------------------------------------


class TestThaw:
    def test_persistent_map_to_dict(self):
        pm = PersistentMap(a=1, b=2)
        result = thaw(pm)
        assert isinstance(result, dict)
        assert result == {"a": 1, "b": 2}

    def test_persistent_vector_to_list(self):
        pv = PersistentVector()
        pv = pv.append(10).append(20).append(30)
        result = thaw(pv)
        assert isinstance(result, list)
        assert result == [10, 20, 30]

    def test_nested_thaw(self):
        pm = PersistentMap()
        pm = pm.set("users", PersistentVector().append(PersistentMap(name="Alice")))
        result = thaw(pm)
        assert isinstance(result, dict)
        assert isinstance(result["users"], list)
        assert isinstance(result["users"][0], dict)
        assert result["users"][0]["name"] == "Alice"

    def test_primitives_pass_through(self):
        assert thaw(42) == 42
        assert thaw("hello") == "hello"
        assert thaw(3.14) == 3.14
        assert thaw(None) is None
        assert thaw(True) is True

    def test_empty_map(self):
        result = thaw(PersistentMap())
        assert isinstance(result, dict)
        assert result == {}

    def test_empty_vector(self):
        pv = PersistentVector()
        result = thaw(pv)
        assert isinstance(result, list)
        assert result == []


# ---------------------------------------------------------------------------
# TestRoundTrip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_dict_round_trip(self):
        d = {"a": 1, "b": 2, "c": 3}
        assert thaw(freeze(d)) == d

    def test_nested_round_trip(self):
        d = {
            "name": "Alice",
            "scores": [95, 87, 100],
            "address": {"city": "Springfield", "zip": "12345"},
        }
        assert thaw(freeze(d)) == d

    def test_list_round_trip(self):
        lst = [1, "two", 3.0, None, True]
        assert thaw(freeze(lst)) == lst

    def test_deeply_nested(self):
        d = {"l1": {"l2": {"l3": {"l4": {"l5": "deep"}}}}}
        assert thaw(freeze(d)) == d


# ---------------------------------------------------------------------------
# TestFreezeWithUpdateIn
# ---------------------------------------------------------------------------

# Skip if with_update is not importable (e.g. running only persistent-collections
# tests without the with-update package on PYTHONPATH).
with_update_mod = pytest.importorskip(
    "with_update",
    reason="with-update package not available",
)
update_in = with_update_mod.update_in
updatable = with_update_mod.updatable


@updatable
@dataclass(frozen=True)
class StateRecord:
    data: Any = None


class TestFreezeWithUpdateIn:
    def test_update_in_on_frozen_dict(self):
        """Freeze a plain dict, assign to a dataclass field, use update_in to update a key."""
        plain = {"count": 0, "label": "hello"}
        frozen = freeze(plain)
        rec = StateRecord(data=frozen)

        result = update_in(rec, ["data", "count"], 99)

        assert result.data["count"] == 99
        assert result.data["label"] == "hello"
        # Original record is unchanged
        assert rec.data["count"] == 0

    def test_update_in_on_frozen_nested_dict(self):
        """Deeper nesting: freeze a nested plain dict, navigate two levels with update_in."""
        plain = {"config": {"timeout": 30, "retries": 3}, "active": True}
        frozen = freeze(plain)
        rec = StateRecord(data=frozen)

        result = update_in(rec, ["data", "config", "timeout"], 60)

        assert result.data["config"]["timeout"] == 60
        assert result.data["config"]["retries"] == 3
        assert result.data["active"] is True
        # Original is unchanged
        assert rec.data["config"]["timeout"] == 30
