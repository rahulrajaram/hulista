"""PersistentMap — immutable, hashable mapping with O(log32 n) structural-sharing updates."""
from __future__ import annotations

import collections.abc
from persistent_collections._hamt import EMPTY_BITMAP_NODE, _hash_fold


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
        hash_val = _hash_fold(hash(key))
        new_root, added = self._root.assoc(0, hash_val, key, value)
        if new_root is self._root:
            return self
        new_count = self._count + (1 if added else 0)
        return PersistentMap(new_root, new_count)

    def delete(self, key) -> PersistentMap:
        hash_val = _hash_fold(hash(key))
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
        hash_val = _hash_fold(hash(key))
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

    def transient(self) -> TransientMap:
        """Return a mutable transient builder for batch construction.

        Usage::

            m = PersistentMap()
            with m.transient() as t:
                for k, v in data.items():
                    t[k] = v
            m2 = t.persistent()
        """
        return TransientMap(self)


class TransientMap:
    """Mutable builder for PersistentMap — batch construction without structural copies.

    Use as a context manager or call .persistent() to freeze.
    """
    __slots__ = ('_root', '_count', '_frozen')

    def __init__(self, source: PersistentMap | None = None):
        if source is not None:
            self._root = source._root
            self._count = source._count
        else:
            self._root = EMPTY_BITMAP_NODE
            self._count = 0
        self._frozen = False

    def _check_mutable(self):
        if self._frozen:
            raise RuntimeError("TransientMap has been frozen; call transient() again")

    def __setitem__(self, key, value):
        self._check_mutable()
        hash_val = _hash_fold(hash(key))
        new_root, added = self._root.assoc(0, hash_val, key, value)
        self._root = new_root
        if added:
            self._count += 1

    def __delitem__(self, key):
        self._check_mutable()
        hash_val = _hash_fold(hash(key))
        new_root = self._root.without(0, hash_val, key)
        if new_root is None:
            self._root = EMPTY_BITMAP_NODE
        else:
            self._root = new_root
        self._count -= 1

    def __getitem__(self, key):
        hash_val = _hash_fold(hash(key))
        return self._root.find(0, hash_val, key)

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __len__(self):
        return self._count

    def persistent(self) -> PersistentMap:
        """Freeze this transient and return an immutable PersistentMap."""
        self._frozen = True
        return PersistentMap(self._root, self._count)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
