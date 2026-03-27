"""Tests for TransientMap."""
from __future__ import annotations

import pytest

from persistent_collections.persistent_map import PersistentMap, TransientMap


# ---------------------------------------------------------------------------
# Basic set and get via __setitem__ / __getitem__
# ---------------------------------------------------------------------------

class TestSetAndGet:
    def test_setitem_and_getitem(self):
        t = TransientMap()
        t["key"] = "value"
        assert t["key"] == "value"

    def test_multiple_keys(self):
        t = TransientMap()
        t["a"] = 1
        t["b"] = 2
        t["c"] = 3
        assert t["a"] == 1
        assert t["b"] == 2
        assert t["c"] == 3

    def test_overwrite_key(self):
        t = TransientMap()
        t["k"] = "first"
        t["k"] = "second"
        assert t["k"] == "second"

    def test_missing_key_raises_key_error(self):
        t = TransientMap()
        with pytest.raises(KeyError):
            _ = t["missing"]

    def test_integer_keys(self):
        t = TransientMap()
        for i in range(20):
            t[i] = i * i
        for i in range(20):
            assert t[i] == i * i

    def test_len_reflects_insertions(self):
        t = TransientMap()
        assert len(t) == 0
        t["x"] = 1
        assert len(t) == 1
        t["y"] = 2
        assert len(t) == 2

    def test_len_does_not_double_count_overwrites(self):
        t = TransientMap()
        t["k"] = 1
        t["k"] = 2
        assert len(t) == 1

    def test_contains_after_set(self):
        t = TransientMap()
        t["present"] = True
        assert "present" in t
        assert "absent" not in t


# ---------------------------------------------------------------------------
# __delitem__
# ---------------------------------------------------------------------------

class TestDelItem:
    def test_delitem_removes_key(self):
        t = TransientMap()
        t["k"] = "v"
        del t["k"]
        assert "k" not in t

    def test_delitem_reduces_len(self):
        t = TransientMap()
        t["a"] = 1
        t["b"] = 2
        del t["a"]
        assert len(t) == 1

    def test_delitem_only_removes_target_key(self):
        t = TransientMap()
        t["a"] = 1
        t["b"] = 2
        del t["a"]
        assert t["b"] == 2

    def test_getitem_after_delete_raises(self):
        t = TransientMap()
        t["gone"] = "bye"
        del t["gone"]
        with pytest.raises(KeyError):
            _ = t["gone"]

    def test_delete_and_reinsert(self):
        t = TransientMap()
        t["k"] = "original"
        del t["k"]
        t["k"] = "new"
        assert t["k"] == "new"


# ---------------------------------------------------------------------------
# persistent() — freezes the transient
# ---------------------------------------------------------------------------

class TestPersistent:
    def test_persistent_returns_persistent_map(self):
        t = TransientMap()
        t["a"] = 1
        pm = t.persistent()
        assert isinstance(pm, PersistentMap)

    def test_persistent_map_has_correct_values(self):
        t = TransientMap()
        t["x"] = 10
        t["y"] = 20
        pm = t.persistent()
        assert pm["x"] == 10
        assert pm["y"] == 20

    def test_persistent_map_has_correct_len(self):
        t = TransientMap()
        for i in range(5):
            t[i] = i
        pm = t.persistent()
        assert len(pm) == 5

    def test_persistent_map_is_immutable(self):
        t = TransientMap()
        t["k"] = 1
        pm = t.persistent()
        # PersistentMap.set() returns a new map — the original is unchanged
        pm2 = pm.set("new", 99)
        assert "new" not in pm
        assert pm2["new"] == 99


# ---------------------------------------------------------------------------
# Frozen transient raises on mutation
# ---------------------------------------------------------------------------

class TestFrozenTransient:
    def test_setitem_after_persistent_raises(self):
        t = TransientMap()
        t["k"] = 1
        t.persistent()  # freezes
        with pytest.raises(RuntimeError):
            t["k2"] = 2

    def test_delitem_after_persistent_raises(self):
        t = TransientMap()
        t["k"] = 1
        t.persistent()  # freezes
        with pytest.raises(RuntimeError):
            del t["k"]

    def test_read_still_works_after_frozen(self):
        """Reads should still work even after freezing."""
        t = TransientMap()
        t["key"] = "value"
        t.persistent()
        # Reading is not guarded — it should succeed
        assert t["key"] == "value"

    def test_error_message_mentions_frozen(self):
        t = TransientMap()
        t.persistent()
        with pytest.raises(RuntimeError, match="frozen"):
            t["x"] = 1


# ---------------------------------------------------------------------------
# Context manager usage
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_basic(self):
        t = TransientMap()
        with t as tm:
            tm["a"] = 1
            tm["b"] = 2
        pm = t.persistent()
        assert pm["a"] == 1
        assert pm["b"] == 2

    def test_context_manager_returns_self(self):
        t = TransientMap()
        with t as tm:
            assert tm is t

    def test_context_manager_does_not_freeze_on_exit(self):
        """__exit__ does NOT freeze — you still call .persistent() yourself."""
        t = TransientMap()
        with t:
            t["k"] = "v"
        # After the with-block, the transient is NOT yet frozen
        t["k2"] = "v2"  # should not raise
        pm = t.persistent()
        assert pm["k"] == "v"
        assert pm["k2"] == "v2"

    def test_context_manager_with_many_keys(self):
        t = TransientMap()
        with t as tm:
            for i in range(50):
                tm[i] = i ** 2
        pm = t.persistent()
        assert len(pm) == 50
        assert pm[7] == 49

    def test_context_manager_exception_propagates(self):
        t = TransientMap()
        with pytest.raises(ValueError):
            with t as tm:
                tm["k"] = 1
                raise ValueError("oops")
        # After exception, the transient still holds what was inserted
        assert t["k"] == 1


# ---------------------------------------------------------------------------
# Building from an existing PersistentMap
# ---------------------------------------------------------------------------

class TestFromPersistentMap:
    def test_transient_from_existing_map(self):
        pm = PersistentMap.from_dict({"a": 1, "b": 2})
        t = TransientMap(pm)
        assert t["a"] == 1
        assert t["b"] == 2

    def test_transient_inherits_len(self):
        pm = PersistentMap.from_dict({"x": 10, "y": 20, "z": 30})
        t = TransientMap(pm)
        assert len(t) == 3

    def test_transient_can_add_to_existing(self):
        pm = PersistentMap.from_dict({"base": 0})
        t = TransientMap(pm)
        t["new"] = 99
        result = t.persistent()
        assert result["base"] == 0
        assert result["new"] == 99
        assert len(result) == 2

    def test_transient_can_overwrite_existing(self):
        pm = PersistentMap.from_dict({"k": "old"})
        t = TransientMap(pm)
        t["k"] = "new"
        result = t.persistent()
        assert result["k"] == "new"
        assert len(result) == 1

    def test_transient_can_delete_from_existing(self):
        pm = PersistentMap.from_dict({"a": 1, "b": 2})
        t = TransientMap(pm)
        del t["a"]
        result = t.persistent()
        assert "a" not in result
        assert result["b"] == 2

    def test_original_map_unchanged_after_transient_mutations(self):
        """The source PersistentMap must not be affected by transient mutations."""
        pm = PersistentMap.from_dict({"a": 1})
        t = pm.transient()
        t["a"] = 999
        t["b"] = 2
        # original pm is still intact
        assert pm["a"] == 1
        assert "b" not in pm

    def test_persistent_map_transient_method(self):
        """PersistentMap.transient() is equivalent to TransientMap(pm)."""
        pm = PersistentMap.from_dict({"x": 1})
        t = pm.transient()
        assert isinstance(t, TransientMap)
        assert t["x"] == 1

    def test_empty_source_map(self):
        pm = PersistentMap()
        t = TransientMap(pm)
        assert len(t) == 0
        t["first"] = "value"
        result = t.persistent()
        assert result["first"] == "value"
