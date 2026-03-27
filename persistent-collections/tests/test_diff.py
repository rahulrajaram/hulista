"""Tests for structural diff of PersistentMap."""
from __future__ import annotations

import pytest

from persistent_collections.persistent_map import PersistentMap
from persistent_collections._diff import diff, Change, ChangeType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_map(**kwargs) -> PersistentMap:
    return PersistentMap.from_dict(kwargs)


def changes_by_key(changes) -> dict:
    """Convert an iterable of Change objects into {key: Change} for easy lookup."""
    return {c.key: c for c in changes}


# ---------------------------------------------------------------------------
# Identical maps — empty result
# ---------------------------------------------------------------------------

class TestIdenticalMaps:
    def test_same_object_yields_no_changes(self):
        pm = make_map(a=1, b=2)
        result = list(diff(pm, pm))
        assert result == []

    def test_equal_maps_with_same_content_yields_no_changes(self):
        pm1 = make_map(x=10, y=20)
        pm2 = make_map(x=10, y=20)
        result = list(diff(pm1, pm2))
        assert result == []

    def test_both_empty_yields_no_changes(self):
        pm1 = PersistentMap()
        pm2 = PersistentMap()
        result = list(diff(pm1, pm2))
        assert result == []

    def test_single_key_identical(self):
        pm = make_map(only="value")
        result = list(diff(pm, pm))
        assert result == []


# ---------------------------------------------------------------------------
# Added keys
# ---------------------------------------------------------------------------

class TestAddedKeys:
    def test_single_key_added(self):
        pm1 = make_map(a=1)
        pm2 = make_map(a=1, b=2)
        changes = changes_by_key(diff(pm1, pm2))
        assert "b" in changes
        c = changes["b"]
        assert c.type == ChangeType.ADDED
        assert c.new_value == 2
        assert c.old_value is None

    def test_multiple_keys_added(self):
        pm1 = make_map(a=1)
        pm2 = make_map(a=1, b=2, c=3, d=4)
        changes = changes_by_key(diff(pm1, pm2))
        assert set(changes.keys()) == {"b", "c", "d"}
        for key in ("b", "c", "d"):
            assert changes[key].type == ChangeType.ADDED

    def test_all_keys_added(self):
        pm1 = PersistentMap()
        pm2 = make_map(x=10, y=20)
        changes = changes_by_key(diff(pm1, pm2))
        assert set(changes.keys()) == {"x", "y"}
        assert all(c.type == ChangeType.ADDED for c in changes.values())

    def test_added_change_has_correct_new_value(self):
        pm1 = PersistentMap()
        pm2 = make_map(key="hello")
        changes = list(diff(pm1, pm2))
        assert len(changes) == 1
        assert changes[0].new_value == "hello"
        assert changes[0].old_value is None


# ---------------------------------------------------------------------------
# Removed keys
# ---------------------------------------------------------------------------

class TestRemovedKeys:
    def test_single_key_removed(self):
        pm1 = make_map(a=1, b=2)
        pm2 = make_map(a=1)
        changes = changes_by_key(diff(pm1, pm2))
        assert "b" in changes
        c = changes["b"]
        assert c.type == ChangeType.REMOVED
        assert c.old_value == 2
        assert c.new_value is None

    def test_multiple_keys_removed(self):
        pm1 = make_map(a=1, b=2, c=3, d=4)
        pm2 = make_map(a=1)
        changes = changes_by_key(diff(pm1, pm2))
        assert set(changes.keys()) == {"b", "c", "d"}
        for key in ("b", "c", "d"):
            assert changes[key].type == ChangeType.REMOVED

    def test_all_keys_removed(self):
        pm1 = make_map(x=10, y=20)
        pm2 = PersistentMap()
        changes = changes_by_key(diff(pm1, pm2))
        assert set(changes.keys()) == {"x", "y"}
        assert all(c.type == ChangeType.REMOVED for c in changes.values())

    def test_removed_change_has_correct_old_value(self):
        pm1 = make_map(key="bye")
        pm2 = PersistentMap()
        changes = list(diff(pm1, pm2))
        assert len(changes) == 1
        assert changes[0].old_value == "bye"
        assert changes[0].new_value is None


# ---------------------------------------------------------------------------
# Modified values
# ---------------------------------------------------------------------------

class TestModifiedValues:
    def test_single_key_modified(self):
        pm1 = make_map(a=1)
        pm2 = make_map(a=2)
        changes = changes_by_key(diff(pm1, pm2))
        assert "a" in changes
        c = changes["a"]
        assert c.type == ChangeType.MODIFIED
        assert c.old_value == 1
        assert c.new_value == 2

    def test_multiple_keys_modified(self):
        pm1 = make_map(a=1, b=2, c=3)
        pm2 = make_map(a=10, b=20, c=30)
        changes = changes_by_key(diff(pm1, pm2))
        assert set(changes.keys()) == {"a", "b", "c"}
        for key, (old, new) in [("a", (1, 10)), ("b", (2, 20)), ("c", (3, 30))]:
            c = changes[key]
            assert c.type == ChangeType.MODIFIED
            assert c.old_value == old
            assert c.new_value == new

    def test_unchanged_keys_not_reported(self):
        pm1 = make_map(keep=99, change=1)
        pm2 = make_map(keep=99, change=2)
        changes = changes_by_key(diff(pm1, pm2))
        assert "keep" not in changes
        assert "change" in changes

    def test_modified_change_repr(self):
        pm1 = make_map(k=1)
        pm2 = make_map(k=2)
        changes = list(diff(pm1, pm2))
        r = repr(changes[0])
        assert "MODIFIED" in r
        assert "k" in r


# ---------------------------------------------------------------------------
# Mixed changes
# ---------------------------------------------------------------------------

class TestMixedChanges:
    def test_add_remove_modify_together(self):
        pm1 = make_map(keep=1, remove_me=2, change_me=3)
        pm2 = make_map(keep=1, added=99, change_me=30)
        changes = changes_by_key(diff(pm1, pm2))

        assert "keep" not in changes

        assert "remove_me" in changes
        assert changes["remove_me"].type == ChangeType.REMOVED
        assert changes["remove_me"].old_value == 2

        assert "added" in changes
        assert changes["added"].type == ChangeType.ADDED
        assert changes["added"].new_value == 99

        assert "change_me" in changes
        assert changes["change_me"].type == ChangeType.MODIFIED
        assert changes["change_me"].old_value == 3
        assert changes["change_me"].new_value == 30

    def test_exactly_three_changes(self):
        pm1 = make_map(a=1, b=2, c=3)
        pm2 = make_map(a=10, b=2, d=4)
        changes = list(diff(pm1, pm2))
        assert len(changes) == 3  # a modified, c removed, d added

    def test_diff_is_not_symmetric(self):
        pm1 = make_map(a=1)
        pm2 = make_map(b=2)
        forward = changes_by_key(diff(pm1, pm2))
        backward = changes_by_key(diff(pm2, pm1))

        assert forward["a"].type == ChangeType.REMOVED
        assert forward["b"].type == ChangeType.ADDED

        assert backward["a"].type == ChangeType.ADDED
        assert backward["b"].type == ChangeType.REMOVED

    def test_diff_large_map(self):
        """Smoke test with a large number of keys."""
        base = {str(i): i for i in range(100)}
        pm1 = PersistentMap.from_dict(base)

        updated = dict(base)
        updated["50"] = 9999       # modify
        del updated["75"]          # remove
        updated["new_key"] = -1    # add

        pm2 = PersistentMap.from_dict(updated)
        changes = changes_by_key(diff(pm1, pm2))

        assert changes["50"].type == ChangeType.MODIFIED
        assert changes["50"].old_value == 50
        assert changes["50"].new_value == 9999

        assert changes["75"].type == ChangeType.REMOVED
        assert changes["75"].old_value == 75

        assert changes["new_key"].type == ChangeType.ADDED
        assert changes["new_key"].new_value == -1

        # No other changes
        assert len(changes) == 3


# ---------------------------------------------------------------------------
# Diff of empty maps
# ---------------------------------------------------------------------------

class TestEmptyMaps:
    def test_both_empty_no_changes(self):
        result = list(diff(PersistentMap(), PersistentMap()))
        assert result == []

    def test_empty_to_nonempty_all_added(self):
        pm1 = PersistentMap()
        pm2 = make_map(a=1, b=2)
        changes = list(diff(pm1, pm2))
        assert all(c.type == ChangeType.ADDED for c in changes)
        assert len(changes) == 2

    def test_nonempty_to_empty_all_removed(self):
        pm1 = make_map(a=1, b=2)
        pm2 = PersistentMap()
        changes = list(diff(pm1, pm2))
        assert all(c.type == ChangeType.REMOVED for c in changes)
        assert len(changes) == 2


# ---------------------------------------------------------------------------
# Change dataclass — frozen/immutable
# ---------------------------------------------------------------------------

class TestChangeDataclass:
    def test_change_is_frozen(self):
        c = Change(ChangeType.ADDED, "key", new_value=1)
        with pytest.raises((AttributeError, TypeError)):
            c.key = "other"  # type: ignore[misc]

    def test_change_added_repr(self):
        c = Change(ChangeType.ADDED, "k", new_value=42)
        r = repr(c)
        assert "ADDED" in r
        assert "k" in r
        assert "42" in r

    def test_change_removed_repr(self):
        c = Change(ChangeType.REMOVED, "k", old_value=99)
        r = repr(c)
        assert "REMOVED" in r
        assert "99" in r

    def test_change_modified_repr(self):
        c = Change(ChangeType.MODIFIED, "k", old_value=1, new_value=2)
        r = repr(c)
        assert "MODIFIED" in r
        assert "1" in r
        assert "2" in r

    def test_change_type_enum_values(self):
        assert ChangeType.ADDED.value == "added"
        assert ChangeType.REMOVED.value == "removed"
        assert ChangeType.MODIFIED.value == "modified"
