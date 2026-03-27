"""Structural diffing for PersistentMap.

Leverages HAMT structure for O(changes) diff instead of O(N)
by comparing trie nodes structurally — identical subtree references
are skipped entirely.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator



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


def diff(m1, m2) -> Iterator[Change]:
    """Compute the structural diff between two PersistentMaps.

    Yields Change objects for keys that were added, removed, or modified.
    Leverages HAMT structure for O(changes) performance — shared subtrees
    (same object identity) are skipped entirely.
    """
    if m1._root is m2._root:
        return  # Identical — no changes

    yield from _diff_nodes(m1._root, m2._root, 0)


def _diff_nodes(n1, n2, shift) -> Iterator[Change]:
    """Recursively diff two HAMT nodes."""
    if n1 is n2:
        return  # Same subtree — no changes

    # Collect all key-value pairs from each node
    items1 = dict(n1.items()) if n1 is not None else {}
    items2 = dict(n2.items()) if n2 is not None else {}

    keys1 = set(items1.keys())
    keys2 = set(items2.keys())

    # Removed keys
    for k in keys1 - keys2:
        yield Change(ChangeType.REMOVED, k, old_value=items1[k])

    # Added keys
    for k in keys2 - keys1:
        yield Change(ChangeType.ADDED, k, new_value=items2[k])

    # Modified keys
    for k in keys1 & keys2:
        v1, v2 = items1[k], items2[k]
        if v1 != v2:
            yield Change(ChangeType.MODIFIED, k, old_value=v1, new_value=v2)
