"""PersistentSet — immutable, hashable set backed by HAMT."""
from __future__ import annotations

import collections.abc
from typing import Any, Iterator

from persistent_collections._hamt import EMPTY_BITMAP_NODE, _hash_fold

# Sentinel value stored for every element (we only care about keys).
_PRESENT: object = object()


class PersistentSet(collections.abc.Set):
    """Immutable set with structural sharing via HAMT.

    All mutating operations return a new PersistentSet; the original is
    never modified.  O(log32 n) for membership test, add, and discard.
    """
    __slots__ = ('_root', '_count', '_hash_cache')

    # Typed slot declarations so mypy can resolve attribute access.
    _root: Any
    _count: int
    _hash_cache: int | None

    def __init__(self, iterable: collections.abc.Iterable[Any] | None = None) -> None:
        object.__setattr__(self, '_root', EMPTY_BITMAP_NODE)
        object.__setattr__(self, '_count', 0)
        object.__setattr__(self, '_hash_cache', None)

        if iterable is not None:
            s: PersistentSet = self
            for elem in iterable:
                s = s.add(elem)
            object.__setattr__(self, '_root', s._root)
            object.__setattr__(self, '_count', s._count)

    # ------------------------------------------------------------------
    # Internal fast constructor
    # ------------------------------------------------------------------

    @classmethod
    def _make(cls, root: Any, count: int) -> PersistentSet:
        s = object.__new__(cls)
        object.__setattr__(s, '_root', root)
        object.__setattr__(s, '_count', count)
        object.__setattr__(s, '_hash_cache', None)
        return s

    # ------------------------------------------------------------------
    # Core mutating operations (return new sets)
    # ------------------------------------------------------------------

    def add(self, elem: Any) -> PersistentSet:
        """Return a new set with *elem* included."""
        hash_val = _hash_fold(hash(elem))
        new_root, added = self._root.assoc(0, hash_val, elem, _PRESENT)
        if new_root is self._root:
            return self
        return PersistentSet._make(new_root, self._count + (1 if added else 0))

    def discard(self, elem: Any) -> PersistentSet:
        """Return a new set with *elem* removed (no-op if absent)."""
        hash_val = _hash_fold(hash(elem))
        try:
            new_root = self._root.without(0, hash_val, elem)
        except KeyError:
            return self
        if new_root is None:
            return PersistentSet()
        if new_root is self._root:
            return self
        return PersistentSet._make(new_root, self._count - 1)

    # ------------------------------------------------------------------
    # Abstract methods required by collections.abc.Set
    # ------------------------------------------------------------------

    def __contains__(self, elem: object) -> bool:
        try:
            hash_val = _hash_fold(hash(elem))
            self._root.find(0, hash_val, elem)
            return True
        except (KeyError, TypeError):
            return False

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Iterator[Any]:
        for key, _val in self._root.items():
            yield key

    # ------------------------------------------------------------------
    # Set algebra — return PersistentSet, not frozenset
    # ------------------------------------------------------------------

    def __and__(self, other: Any) -> PersistentSet:
        """Intersection: elements present in both sets."""
        if not isinstance(other, collections.abc.Set):
            return NotImplemented
        result = PersistentSet()
        for elem in self:
            if elem in other:
                result = result.add(elem)
        return result

    def __or__(self, other: Any) -> PersistentSet:
        """Union: elements present in either set."""
        if not isinstance(other, collections.abc.Set):
            return NotImplemented
        result: PersistentSet = self
        for elem in other:
            result = result.add(elem)
        return result

    def __sub__(self, other: Any) -> PersistentSet:
        """Difference: elements in self but not in other."""
        if not isinstance(other, collections.abc.Set):
            return NotImplemented
        result: PersistentSet = self
        for elem in other:
            result = result.discard(elem)
        return result

    def __xor__(self, other: Any) -> PersistentSet:
        """Symmetric difference: elements in exactly one of the sets."""
        if not isinstance(other, collections.abc.Set):
            return NotImplemented
        return (self | other) - (self & other)

    # ------------------------------------------------------------------
    # Subset / superset predicates
    # ------------------------------------------------------------------

    def issubset(self, other: collections.abc.Set) -> bool:
        """Return True if every element of self is in *other*."""
        if len(self) > len(other):
            return False
        return all(elem in other for elem in self)

    def issuperset(self, other: collections.abc.Set) -> bool:
        """Return True if every element of *other* is in self."""
        return all(elem in self for elem in other)

    # ------------------------------------------------------------------
    # Hashing and equality
    # ------------------------------------------------------------------

    def __hash__(self) -> int:
        h = self._hash_cache
        if h is None:
            h = hash(frozenset(self))
            object.__setattr__(self, '_hash_cache', h)
        return h

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PersistentSet):
            if self._count != other._count:
                return False
            if self._root is other._root:
                return True
        if isinstance(other, collections.abc.Set):
            if len(self) != len(other):
                return False
            return all(elem in other for elem in self)
        return NotImplemented

    # ------------------------------------------------------------------
    # Immutability guard
    # ------------------------------------------------------------------

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("PersistentSet is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("PersistentSet is immutable")

    def __repr__(self) -> str:
        items = ', '.join(repr(e) for e in self)
        return f'PersistentSet({{{items}}})'
