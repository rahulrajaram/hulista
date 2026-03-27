"""PersistentMap — immutable, hashable mapping with O(log32 n) structural-sharing updates."""
from __future__ import annotations

import collections.abc
from persistent_collections._hamt import _BitmapNode, EMPTY_BITMAP_NODE


class PersistentMap(collections.abc.Mapping):
    """Immutable mapping with structural sharing.

    All update operations return a new PersistentMap sharing
    unchanged subtrees with the original. O(log32 n) for
    get, set, and delete operations.
    """
    __slots__ = ('_root', '_count', '_hash')

    def __init__(self, _root=EMPTY_BITMAP_NODE, _count=0, /, **kwargs):
        object.__setattr__(self, '_root', _root)
        object.__setattr__(self, '_count', _count)
        object.__setattr__(self, '_hash', None)
        if kwargs:
            m = self
            for k, v in kwargs.items():
                m = m.set(k, v)
            object.__setattr__(self, '_root', m._root)
            object.__setattr__(self, '_count', m._count)

    @classmethod
    def from_dict(cls, d: dict) -> PersistentMap:
        m = cls()
        for k, v in d.items():
            m = m.set(k, v)
        return m

    def set(self, key, value) -> PersistentMap:
        hash_val = hash(key) & 0xFFFFFFFF
        new_root = self._root.assoc(0, hash_val, key, value)
        if new_root is self._root:
            return self
        # Check if key was new or replaced
        try:
            self._root.find(0, hash_val, key)
            new_count = self._count  # Replacement
        except KeyError:
            new_count = self._count + 1  # New key
        return PersistentMap(new_root, new_count)

    def delete(self, key) -> PersistentMap:
        hash_val = hash(key) & 0xFFFFFFFF
        new_root = self._root.without(0, hash_val, key)
        if new_root is None:
            return PersistentMap()
        if new_root is self._root:
            return self
        return PersistentMap(new_root, self._count - 1)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key):
        hash_val = hash(key) & 0xFFFFFFFF
        return self._root.find(0, hash_val, key)

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __len__(self):
        return self._count

    def __iter__(self):
        for k, v in self._root.items():
            yield k

    def __hash__(self):
        h = self._hash
        if h is None:
            h = hash(frozenset(self._root.items()))
            object.__setattr__(self, '_hash', h)
        return h

    def __eq__(self, other):
        if isinstance(other, PersistentMap):
            if self._count != other._count:
                return False
            if self._root is other._root:
                return True
        if isinstance(other, collections.abc.Mapping):
            if len(self) != len(other):
                return False
            for k, v in self.items():
                try:
                    if other[k] != v:
                        return False
                except KeyError:
                    return False
            return True
        return NotImplemented

    def __repr__(self):
        items = ', '.join(f'{k!r}: {v!r}' for k, v in self.items())
        return f'PersistentMap({{{items}}})'

    def __setattr__(self, name, value):
        raise AttributeError("PersistentMap is immutable")

    def __delattr__(self, name):
        raise AttributeError("PersistentMap is immutable")
