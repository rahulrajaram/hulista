from __future__ import annotations

from persistent_collections._diff import ChangeType, _diff_array_array, _diff_bitmap_bitmap, _diff_collision_collision, _diff_mixed, _diff_nodes
from persistent_collections._hamt import _ArrayNode, _BitmapNode, _CollisionNode


def test_diff_nodes_handles_none_and_empty_bitmap() -> None:
    added = list(_diff_nodes(None, _BitmapNode(1, ("a", 1)), 0))
    removed = list(_diff_nodes(_BitmapNode(1, ("a", 1)), _BitmapNode(0, ()), 0))

    assert added[0].type == ChangeType.ADDED
    assert removed[0].type == ChangeType.REMOVED


def test_diff_bitmap_bitmap_handles_leaf_vs_subnode_materialization() -> None:
    left = _BitmapNode(1, ("a", 1))
    right_subnode = _BitmapNode(1, ("a", 2))
    right = _BitmapNode(1, (None, right_subnode))

    changes = list(_diff_bitmap_bitmap(left, right, 0))

    assert {change.type for change in changes} == {ChangeType.MODIFIED}
    assert changes[0].key == "a"


def test_diff_bitmap_bitmap_handles_subnode_add_and_remove() -> None:
    subnode = _BitmapNode(1, ("a", 1))
    removed = list(_diff_bitmap_bitmap(_BitmapNode(1, (None, subnode)), _BitmapNode(0, ()), 0))
    added = list(_diff_bitmap_bitmap(_BitmapNode(0, ()), _BitmapNode(1, (None, subnode)), 0))

    assert removed[0].type == ChangeType.REMOVED
    assert added[0].type == ChangeType.ADDED


def test_diff_array_array_covers_leaf_subnode_cases() -> None:
    left = _ArrayNode(
        4,
        [
            ("a", 1),
            None,
            _BitmapNode(1, ("b", 2)),
            ("c", 3),
        ] + [None] * 28,
    )
    right = _ArrayNode(
        4,
        [
            ("a", 10),
            ("d", 4),
            ("b", 2),
            _BitmapNode(1, ("e", 5)),
        ] + [None] * 28,
    )

    changes = list(_diff_array_array(left, right, 0))
    by_key = {change.key: change for change in changes}

    assert by_key["a"].type == ChangeType.MODIFIED
    assert by_key["d"].type == ChangeType.ADDED
    assert by_key["c"].type == ChangeType.REMOVED
    assert by_key["e"].type == ChangeType.ADDED
    assert "b" not in by_key


def test_diff_array_array_preserves_shared_keys_inside_leaf_subnode_transitions() -> None:
    left = _ArrayNode(
        2,
        [
            ("shared-left", 1),
            _BitmapNode(0b11, ("shared-right", 2, "removed", 3)),
        ] + [None] * 30,
    )
    right = _ArrayNode(
        2,
        [
            _BitmapNode(0b11, ("shared-left", 1, "added", 4)),
            ("shared-right", 2),
        ] + [None] * 30,
    )

    changes = list(_diff_array_array(left, right, 0))
    by_key = {change.key: change for change in changes}

    assert by_key["added"].type == ChangeType.ADDED
    assert by_key["removed"].type == ChangeType.REMOVED
    assert "shared-left" not in by_key
    assert "shared-right" not in by_key


def test_diff_collision_collision_matches_identity_aware_keys() -> None:
    class Key:
        def __init__(self, value: str) -> None:
            self.value = value

        def __hash__(self) -> int:
            return 1

        def __eq__(self, other: object) -> bool:
            return isinstance(other, Key) and self.value == other.value

    first = Key("same")
    second = Key("other")
    left = _CollisionNode(1, ((first, 1), (second, 2)))
    right = _CollisionNode(1, ((first, 10),))

    changes = list(_diff_collision_collision(left, right))
    by_key = {change.key: change for change in changes}

    assert by_key[first].type == ChangeType.MODIFIED
    assert by_key[second].type == ChangeType.REMOVED


def test_diff_mixed_matches_and_adds_entries() -> None:
    left = _BitmapNode(1, ("a", 1))
    right = _ArrayNode(2, [("a", 10), ("b", 2)] + [None] * 30)

    changes = list(_diff_mixed(left, right, 0))
    by_key = {change.key: change for change in changes}

    assert by_key["a"].type == ChangeType.MODIFIED
    assert by_key["b"].type == ChangeType.ADDED


def test_diff_nodes_dispatches_to_mixed_fallback() -> None:
    changes = list(_diff_nodes(_BitmapNode(1, ("a", 1)), _ArrayNode(1, [("a", 2)] + [None] * 31), 0))
    assert changes[0].type == ChangeType.MODIFIED


def test_diff_bitmap_bitmap_reports_replaced_leaf() -> None:
    left = _BitmapNode(1, ("a", 1))
    right = _BitmapNode(1, ("b", 2))
    changes = list(_diff_bitmap_bitmap(left, right, 0))
    assert {change.type for change in changes} == {ChangeType.ADDED, ChangeType.REMOVED}


def test_diff_array_array_reports_leaf_subnode_removals() -> None:
    left = _ArrayNode(1, [("a", 1)] + [None] * 31)
    right = _ArrayNode(1, [_BitmapNode(1, ("b", 2))] + [None] * 31)
    changes = list(_diff_array_array(left, right, 0))
    assert {change.key for change in changes} == {"a", "b"}
