"""Tests for deep-merge and update_in integration with persistent-collections."""
from __future__ import annotations

import builtins
import dataclasses
from dataclasses import dataclass, field
from typing import Any

import pytest

from with_update import updatable, update_in, with_update

# Skip the entire module if persistent-collections is not importable.
persistent_collections = pytest.importorskip(
    "persistent_collections",
    reason="persistent-collections not installed",
)
PersistentMap = persistent_collections.PersistentMap


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@updatable
@dataclass(frozen=True)
class Record:
    name: str = "default"
    data: Any = None


@updatable
@dataclass(frozen=True)
class Nested:
    meta: Any = None
    value: int = 0


# ---------------------------------------------------------------------------
# with_update(deep=True) — merges dict into PersistentMap fields
# ---------------------------------------------------------------------------


class TestDeepMergeWithUpdate:
    def test_deep_merge_adds_new_keys(self) -> None:
        pm = PersistentMap.from_dict({"a": 1})
        rec = Record(name="x", data=pm)
        result = with_update(rec, deep=True, data={"b": 2})
        assert result.data["a"] == 1
        assert result.data["b"] == 2

    def test_deep_merge_overwrites_existing_key(self) -> None:
        pm = PersistentMap.from_dict({"a": 1, "b": 2})
        rec = Record(name="x", data=pm)
        result = with_update(rec, deep=True, data={"a": 99})
        assert result.data["a"] == 99
        assert result.data["b"] == 2

    def test_deep_merge_empty_dict_leaves_map_unchanged(self) -> None:
        pm = PersistentMap.from_dict({"a": 1})
        rec = Record(name="x", data=pm)
        result = with_update(rec, deep=True, data={})
        assert result.data == pm

    def test_deep_merge_returns_persistent_map(self) -> None:
        pm = PersistentMap.from_dict({"a": 1})
        rec = Record(name="x", data=pm)
        result = with_update(rec, deep=True, data={"b": 2})
        assert isinstance(result.data, PersistentMap)

    def test_deep_merge_original_unchanged(self) -> None:
        pm = PersistentMap.from_dict({"a": 1})
        rec = Record(name="x", data=pm)
        _ = with_update(rec, deep=True, data={"b": 2})
        # Original record and map must be unmodified
        assert rec.data["a"] == 1
        assert "b" not in rec.data
        assert rec.name == "x"

    def test_plain_dict_field_not_deep_merged(self) -> None:
        """When existing field is a plain dict (not PersistentMap), replace it."""
        rec = Record(name="x", data={"a": 1})
        result = with_update(rec, deep=True, data={"b": 2})
        # Should be replaced, not merged
        assert result.data == {"b": 2}
        assert "a" not in result.data

    def test_none_field_not_deep_merged(self) -> None:
        """When existing field is None, just set it."""
        rec = Record(name="x", data=None)
        result = with_update(rec, deep=True, data={"b": 2})
        assert result.data == {"b": 2}

    def test_non_dict_new_value_on_persistent_map_field_replaces(self) -> None:
        """When new value is not a dict, even for a PersistentMap field, replace."""
        pm = PersistentMap.from_dict({"a": 1})
        new_pm = PersistentMap.from_dict({"z": 99})
        rec = Record(name="x", data=pm)
        result = with_update(rec, deep=True, data=new_pm)
        assert result.data == new_pm

    def test_deep_false_replaces_persistent_map_field(self) -> None:
        """Without deep=True the field is replaced, not merged."""
        pm = PersistentMap.from_dict({"a": 1})
        rec = Record(name="x", data=pm)
        result = with_update(rec, data={"b": 2})
        assert result.data == {"b": 2}
        assert not isinstance(result.data, PersistentMap)

    def test_non_map_field_updated_normally_with_deep(self) -> None:
        pm = PersistentMap.from_dict({"a": 1})
        rec = Record(name="old", data=pm)
        result = with_update(rec, deep=True, name="new")
        assert result.name == "new"
        assert result.data == pm

    def test_deep_merge_invalid_field_raises(self) -> None:
        rec = Record(name="x")
        with pytest.raises(TypeError, match="Invalid field"):
            with_update(rec, deep=True, nonexistent="y")


# ---------------------------------------------------------------------------
# with_update(deep=True) — Pydantic model variant
# ---------------------------------------------------------------------------


pydantic = pytest.importorskip("pydantic")


class TestDeepMergePydantic:
    def test_deep_merge_pydantic_persistent_map_field(self) -> None:
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True, "arbitrary_types_allowed": True}
            settings: Any = None

        pm = PersistentMap.from_dict({"k": "v"})
        cfg = Config(settings=pm)
        result = with_update(cfg, deep=True, settings={"extra": 42})
        assert result.settings["k"] == "v"
        assert result.settings["extra"] == 42
        assert isinstance(result.settings, PersistentMap)

    def test_deep_merge_pydantic_original_unchanged(self) -> None:
        from pydantic import BaseModel

        @updatable
        class Config(BaseModel):
            model_config = {"frozen": True, "arbitrary_types_allowed": True}
            settings: Any = None

        pm = PersistentMap.from_dict({"k": "v"})
        cfg = Config(settings=pm)
        _ = with_update(cfg, deep=True, settings={"new": 1})
        assert cfg.settings["k"] == "v"
        assert "new" not in cfg.settings


# ---------------------------------------------------------------------------
# update_in — path-based nested updates
# ---------------------------------------------------------------------------


class TestUpdateIn:
    def test_update_in_top_level_field(self) -> None:
        rec = Record(name="old", data=None)
        result = update_in(rec, ["name"], "new")
        assert result.name == "new"
        assert result.data is None

    def test_update_in_single_level_map(self) -> None:
        pm = PersistentMap.from_dict({"a": 1, "b": 2})
        rec = Record(name="x", data=pm)
        result = update_in(rec, ["data", "a"], 99)
        assert result.data["a"] == 99
        assert result.data["b"] == 2

    def test_update_in_two_level_nested_map(self) -> None:
        inner = PersistentMap.from_dict({"b": 1})
        outer = PersistentMap().set("a", inner)
        rec = Record(name="x", data=outer)
        result = update_in(rec, ["data", "a", "b"], 42)
        assert result.data["a"]["b"] == 42

    def test_update_in_adds_new_key(self) -> None:
        pm = PersistentMap.from_dict({"a": 1})
        rec = Record(name="x", data=pm)
        result = update_in(rec, ["data", "c"], 99)
        assert result.data["a"] == 1
        assert result.data["c"] == 99

    def test_update_in_creates_intermediate_map_for_missing_key(self) -> None:
        pm = PersistentMap()
        rec = Record(name="x", data=pm)
        # "a" doesn't exist yet; _assoc_in will create an empty PersistentMap
        result = update_in(rec, ["data", "a", "b"], 7)
        assert result.data["a"]["b"] == 7

    def test_update_in_original_unchanged(self) -> None:
        pm = PersistentMap.from_dict({"a": 1})
        rec = Record(name="x", data=pm)
        _ = update_in(rec, ["data", "a"], 99)
        assert rec.data["a"] == 1
        assert rec.name == "x"

    def test_update_in_invalid_field_raises(self) -> None:
        rec = Record(name="x")
        with pytest.raises(TypeError, match="Invalid field"):
            update_in(rec, ["nonexistent", "a"], 1)

    def test_update_in_empty_path_raises(self) -> None:
        rec = Record(name="x")
        with pytest.raises(ValueError, match="non-empty"):
            update_in(rec, [], 1)

    def test_update_in_non_map_intermediate_raises(self) -> None:
        rec = Record(name="x", data="not-a-map")
        with pytest.raises(TypeError, match="PersistentMap"):
            update_in(rec, ["data", "key"], 1)


class TestUpdateInPydantic:
    def test_update_in_pydantic_nested_map(self) -> None:
        from pydantic import BaseModel

        @updatable
        class Cfg(BaseModel):
            model_config = {"frozen": True, "arbitrary_types_allowed": True}
            data: Any = None

        pm = PersistentMap.from_dict({"x": 10})
        cfg = Cfg(data=pm)
        result = update_in(cfg, ["data", "x"], 20)
        assert result.data["x"] == 20

    def test_update_in_pydantic_original_unchanged(self) -> None:
        from pydantic import BaseModel

        @updatable
        class Cfg(BaseModel):
            model_config = {"frozen": True, "arbitrary_types_allowed": True}
            data: Any = None

        pm = PersistentMap.from_dict({"x": 10})
        cfg = Cfg(data=pm)
        _ = update_in(cfg, ["data", "x"], 99)
        assert cfg.data["x"] == 10


# ---------------------------------------------------------------------------
# Error when persistent-collections is not available
# ---------------------------------------------------------------------------


class TestMissingPersistentCollections:
    def test_with_update_deep_raises_import_error(self, monkeypatch: Any) -> None:
        """with_update(deep=True) raises ImportError when persistent-collections
        is not installed."""
        import with_update._core as core_module

        monkeypatch.setattr(core_module, "_PERSISTENT_COLLECTIONS_AVAILABLE", False)
        monkeypatch.setattr(core_module, "_PersistentMap", None)

        rec = Record(name="x")
        with pytest.raises(ImportError, match="persistent-collections"):
            with_update(rec, deep=True, name="y")

    def test_update_in_raises_import_error(self, monkeypatch: Any) -> None:
        """update_in raises ImportError when persistent-collections is not installed."""
        import with_update._core as core_module

        monkeypatch.setattr(core_module, "_PERSISTENT_COLLECTIONS_AVAILABLE", False)
        monkeypatch.setattr(core_module, "_PersistentMap", None)

        rec = Record(name="x")
        with pytest.raises(ImportError, match="persistent-collections"):
            update_in(rec, ["name"], "y")

    def test_error_message_mentions_install(self, monkeypatch: Any) -> None:
        import with_update._core as core_module

        monkeypatch.setattr(core_module, "_PERSISTENT_COLLECTIONS_AVAILABLE", False)
        monkeypatch.setattr(core_module, "_PersistentMap", None)

        rec = Record(name="x")
        with pytest.raises(ImportError, match="pip install"):
            with_update(rec, deep=True, name="y")
