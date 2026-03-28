"""Structural diffing for PersistentMap.

Leverages HAMT structure for O(changes) diff instead of O(N)
by comparing trie nodes structurally — identical subtree references
are skipped entirely.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator

from persistent_collections._hamt import (
    _BitmapNode, _CollisionNode, _ArrayNode, _popcount,
    BITS_PER_LEVEL, BRANCH_FACTOR, _keys_equal,
)


class ChangeType(Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass(frozen=True, slots=True)
class Change:
    """A single diff entry between two PersistentMaps."""
    type: ChangeType
    key: Any
    old_value: Any = None
    new_value: Any = None

    def __repr__(self) -> str:
        if self.type == ChangeType.ADDED:
            return f"Change(ADDED, {self.key!r}, new={self.new_value!r})"
        elif self.type == ChangeType.REMOVED:
            return f"Change(REMOVED, {self.key!r}, old={self.old_value!r})"
        else:
            return f"Change(MODIFIED, {self.key!r}, {self.old_value!r} -> {self.new_value!r})"


def diff(m1: Any, m2: Any) -> Iterator[Change]:
    """Compute the structural diff between two PersistentMaps.

    Yields Change objects for keys that were added, removed, or modified.
    Leverages HAMT structure for O(changes) performance — shared subtrees
    (same object identity) are skipped entirely.
    """
    if m1._root is m2._root:
        return  # Identical — no changes

    yield from _diff_nodes(m1._root, m2._root, 0)


def _yield_all(node: Any, change_type: ChangeType) -> Iterator[Change]:
    """Yield all entries in a node as ADDED or REMOVED."""
    for k, v in node.items():
        if change_type == ChangeType.ADDED:
            yield Change(ChangeType.ADDED, k, new_value=v)
        else:
            yield Change(ChangeType.REMOVED, k, old_value=v)


def _diff_nodes(n1: Any, n2: Any, shift: int) -> Iterator[Change]:
    """Recursively diff two HAMT nodes using pairwise structural walk."""
    if n1 is n2:
        return  # Same identity — no changes

    # Handle None (empty) nodes
    if n1 is None or (isinstance(n1, _BitmapNode) and n1.bitmap == 0):
        if n2 is not None and not (isinstance(n2, _BitmapNode) and n2.bitmap == 0):
            yield from _yield_all(n2, ChangeType.ADDED)
        return
    if n2 is None or (isinstance(n2, _BitmapNode) and n2.bitmap == 0):
        yield from _yield_all(n1, ChangeType.REMOVED)
        return

    # Both are BitmapNodes — walk their bitmaps structurally
    if isinstance(n1, _BitmapNode) and isinstance(n2, _BitmapNode):
        yield from _diff_bitmap_bitmap(n1, n2, shift)
    elif isinstance(n1, _ArrayNode) and isinstance(n2, _ArrayNode):
        yield from _diff_array_array(n1, n2, shift)
    elif isinstance(n1, _CollisionNode) and isinstance(n2, _CollisionNode):
        yield from _diff_collision_collision(n1, n2)
    else:
        # Mixed node types — diff by entry extraction on each slot
        yield from _diff_mixed(n1, n2, shift)


def _diff_bitmap_bitmap(n1: _BitmapNode, n2: _BitmapNode, shift: int) -> Iterator[Change]:
    """Diff two BitmapNodes by walking their bitmaps."""
    combined = n1.bitmap | n2.bitmap

    for i in range(BRANCH_FACTOR):
        bit = 1 << i
        if not (combined & bit):
            continue

        in1 = bool(n1.bitmap & bit)
        in2 = bool(n2.bitmap & bit)

        if in1 and in2:
            idx1 = _popcount(n1.bitmap & (bit - 1))
            idx2 = _popcount(n2.bitmap & (bit - 1))
            k1 = n1.array[2 * idx1]
            v1 = n1.array[2 * idx1 + 1]
            k2 = n2.array[2 * idx2]
            v2 = n2.array[2 * idx2 + 1]

            if k1 is None and k2 is None:
                # Both subnodes — recurse
                if v1 is not v2:
                    yield from _diff_nodes(v1, v2, shift + BITS_PER_LEVEL)
            elif k1 is not None and k2 is not None:
                # Both leaves
                if _keys_equal(k1, k2):
                    if v1 != v2:
                        yield Change(ChangeType.MODIFIED, k1, old_value=v1, new_value=v2)
                else:
                    yield Change(ChangeType.REMOVED, k1, old_value=v1)
                    yield Change(ChangeType.ADDED, k2, new_value=v2)
            else:
                # Mixed: one leaf, one subnode — materialize both slots
                d1 = dict([(k1, v1)] if k1 is not None else v1.items())
                d2 = dict([(k2, v2)] if k2 is not None else v2.items())
                for k in set(d1) - set(d2):
                    yield Change(ChangeType.REMOVED, k, old_value=d1[k])
                for k in set(d2) - set(d1):
                    yield Change(ChangeType.ADDED, k, new_value=d2[k])
                for k in set(d1) & set(d2):
                    if d1[k] != d2[k]:
                        yield Change(ChangeType.MODIFIED, k, old_value=d1[k], new_value=d2[k])

        elif in1:
            # Only in n1 — removed
            idx1 = _popcount(n1.bitmap & (bit - 1))
            k1 = n1.array[2 * idx1]
            v1 = n1.array[2 * idx1 + 1]
            if k1 is None:
                yield from _yield_all(v1, ChangeType.REMOVED)
            else:
                yield Change(ChangeType.REMOVED, k1, old_value=v1)

        else:
            # Only in n2 — added
            idx2 = _popcount(n2.bitmap & (bit - 1))
            k2 = n2.array[2 * idx2]
            v2 = n2.array[2 * idx2 + 1]
            if k2 is None:
                yield from _yield_all(v2, ChangeType.ADDED)
            else:
                yield Change(ChangeType.ADDED, k2, new_value=v2)


def _diff_array_array(n1: _ArrayNode, n2: _ArrayNode, shift: int) -> Iterator[Change]:
    """Diff two ArrayNodes by comparing slot-by-slot."""
    for i in range(BRANCH_FACTOR):
        e1 = n1.array[i]
        e2 = n2.array[i]

        if e1 is e2:
            continue  # Same identity — skip

        if e1 is None and e2 is None:
            continue
        elif e1 is None:
            # Added in n2
            if isinstance(e2, tuple):
                yield Change(ChangeType.ADDED, e2[0], new_value=e2[1])
            else:
                yield from _yield_all(e2, ChangeType.ADDED)
        elif e2 is None:
            # Removed from n1
            if isinstance(e1, tuple):
                yield Change(ChangeType.REMOVED, e1[0], old_value=e1[1])
            else:
                yield from _yield_all(e1, ChangeType.REMOVED)
        elif isinstance(e1, tuple) and isinstance(e2, tuple):
            # Both leaves
            if _keys_equal(e1[0], e2[0]):
                if e1[1] != e2[1]:
                    yield Change(ChangeType.MODIFIED, e1[0], old_value=e1[1], new_value=e2[1])
            else:
                yield Change(ChangeType.REMOVED, e1[0], old_value=e1[1])
                yield Change(ChangeType.ADDED, e2[0], new_value=e2[1])
        elif isinstance(e1, tuple):
            # e1 leaf, e2 subnode
            yield Change(ChangeType.REMOVED, e1[0], old_value=e1[1])
            yield from _yield_all(e2, ChangeType.ADDED)
        elif isinstance(e2, tuple):
            # e1 subnode, e2 leaf
            yield from _yield_all(e1, ChangeType.REMOVED)
            yield Change(ChangeType.ADDED, e2[0], new_value=e2[1])
        else:
            # Both subnodes — recurse
            yield from _diff_nodes(e1, e2, shift + BITS_PER_LEVEL)


def _diff_collision_collision(n1: _CollisionNode, n2: _CollisionNode) -> Iterator[Change]:
    """Diff two CollisionNodes."""
    used_in_n2: set[int] = set()
    for k1, v1 in n1.pairs:
        match_index = next(
            (i for i, (k2, _) in enumerate(n2.pairs) if i not in used_in_n2 and _keys_equal(k1, k2)),
            None,
        )
        if match_index is None:
            yield Change(ChangeType.REMOVED, k1, old_value=v1)
            continue
        used_in_n2.add(match_index)
        _, v2 = n2.pairs[match_index]
        if v1 != v2:
            yield Change(ChangeType.MODIFIED, k1, old_value=v1, new_value=v2)

    for i, (k2, v2) in enumerate(n2.pairs):
        if i not in used_in_n2:
            yield Change(ChangeType.ADDED, k2, new_value=v2)


def _diff_mixed(n1: Any, n2: Any, shift: int) -> Iterator[Change]:
    """Diff two nodes of different types by materializing items.

    This is the fallback for mixed node types (e.g., BitmapNode vs ArrayNode).
    Still benefits from identity checks at higher levels.
    """
    del shift
    items1 = list(n1.items())
    items2 = list(n2.items())
    used_in_n2: set[int] = set()

    for k1, v1 in items1:
        match_index = next(
            (i for i, (k2, _) in enumerate(items2) if i not in used_in_n2 and _keys_equal(k1, k2)),
            None,
        )
        if match_index is None:
            yield Change(ChangeType.REMOVED, k1, old_value=v1)
            continue
        used_in_n2.add(match_index)
        _, v2 = items2[match_index]
        if v1 != v2:
            yield Change(ChangeType.MODIFIED, k1, old_value=v1, new_value=v2)

    for i, (k2, v2) in enumerate(items2):
        if i not in used_in_n2:
            yield Change(ChangeType.ADDED, k2, new_value=v2)
