"""PersistentVector — immutable sequence with O(log32 n) structural-sharing updates."""
from __future__ import annotations

import collections.abc
from typing import Iterator

BITS = 5
BRANCH_FACTOR = 1 << BITS  # 32
MASK = BRANCH_FACTOR - 1


class PersistentVector(collections.abc.Sequence):
    """Immutable vector with structural sharing.

    Based on Clojure's persistent vector design:
    - 32-way branching trie for the bulk of elements
    - Tail buffer for the most recent <=32 elements
    - Append, set, and get are all O(log32 n)
    """
    __slots__ = ('_count', '_shift', '_root', '_tail', '_hash')

    def __init__(self, iterable=None):
        object.__setattr__(self, '_count', 0)
        object.__setattr__(self, '_shift', BITS)
        object.__setattr__(self, '_root', ())
        object.__setattr__(self, '_tail', ())
        object.__setattr__(self, '_hash', None)

        if iterable is not None:
            v = self
            for item in iterable:
                v = v.append(item)
            object.__setattr__(self, '_count', v._count)
            object.__setattr__(self, '_shift', v._shift)
            object.__setattr__(self, '_root', v._root)
            object.__setattr__(self, '_tail', v._tail)

    def _tail_offset(self) -> int:
        if self._count < BRANCH_FACTOR:
            return 0
        return ((self._count - 1) >> BITS) << BITS

    def append(self, value) -> PersistentVector:
        """Return a new vector with value appended. O(log32 n)."""
        # Room in tail?
        if self._count - self._tail_offset() < BRANCH_FACTOR:
            new_tail = self._tail + (value,)
            return self._make(self._count + 1, self._shift, self._root, new_tail)

        # Tail is full — push tail into tree, start new tail
        tail_node = self._tail
        new_shift = self._shift

        # Need new root level?
        if (self._count >> BITS) > (1 << self._shift):
            new_root = (self._root, _new_path(self._shift, tail_node))
            new_shift += BITS
        else:
            new_root = _push_tail(self._count, self._shift, self._root, tail_node)

        return self._make(self._count + 1, new_shift, new_root, (value,))

    def set(self, index: int, value) -> PersistentVector:
        """Return a new vector with element at index replaced. O(log32 n)."""
        if index < 0:
            index += self._count
        if not (0 <= index < self._count):
            raise IndexError(f"index {index} out of range for vector of length {self._count}")

        if index >= self._tail_offset():
            # In tail
            tail_idx = index - self._tail_offset()
            new_tail = list(self._tail)
            new_tail[tail_idx] = value
            return self._make(self._count, self._shift, self._root, tuple(new_tail))

        # In tree
        new_root = _assoc_node(self._shift, self._root, index, value)
        return self._make(self._count, self._shift, new_root, self._tail)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return PersistentVector(list(self)[index])
        if index < 0:
            index += self._count
        if not (0 <= index < self._count):
            raise IndexError(f"index {index} out of range")

        if index >= self._tail_offset():
            return self._tail[index - self._tail_offset()]

        # Walk trie
        node = self._root
        for level in range(self._shift, 0, -BITS):
            node = node[(index >> level) & MASK]
        return node[index & MASK]

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Iterator:
        if self._root:
            yield from _iter_node(self._root, self._shift)
        yield from self._tail

    def __hash__(self):
        h = self._hash
        if h is None:
            h = hash(tuple(self))
            object.__setattr__(self, '_hash', h)
        return h

    def __eq__(self, other):
        if isinstance(other, PersistentVector):
            if self._count != other._count:
                return False
            if self._root is other._root and self._tail == other._tail:
                return True
            return all(_values_equal(a, b) for a, b in zip(self, other))
        if isinstance(other, (list, tuple)):
            if len(self) != len(other):
                return False
            return all(_values_equal(a, b) for a, b in zip(self, other))
        if isinstance(other, collections.abc.Sequence) and not isinstance(other, (str, bytes)):
            if len(self) != len(other):
                return False
            return all(_values_equal(a, b) for a, b in zip(self, other))
        return NotImplemented

    def __repr__(self):
        if self._count <= 10:
            items = ', '.join(repr(x) for x in self)
        else:
            items = ', '.join(repr(self[i]) for i in range(10)) + ', ...'
        return f'PersistentVector([{items}])'

    def __add__(self, other):
        if isinstance(other, (PersistentVector, list, tuple)):
            v = self
            for item in other:
                v = v.append(item)
            return v
        return NotImplemented

    def __setattr__(self, name, value):
        raise AttributeError("PersistentVector is immutable")

    def __delattr__(self, name):
        raise AttributeError("PersistentVector is immutable")

    @classmethod
    def _make(cls, count, shift, root, tail):
        v = object.__new__(cls)
        object.__setattr__(v, '_count', count)
        object.__setattr__(v, '_shift', shift)
        object.__setattr__(v, '_root', root)
        object.__setattr__(v, '_tail', tail)
        object.__setattr__(v, '_hash', None)
        return v


def _new_path(shift, node):
    """Create a path from root to leaf for a given node."""
    if shift == 0:
        return node
    return (_new_path(shift - BITS, node),)


def _push_tail(count, shift, root, tail_node):
    """Push a tail node into the trie."""
    subidx = ((count - 1) >> shift) & MASK

    if shift == BITS:
        # Leaf level — insert tail node
        return root + (tail_node,) if subidx >= len(root) else \
               root[:subidx] + (tail_node,) + root[subidx + 1:]

    if subidx < len(root):
        # Recurse into existing child
        new_child = _push_tail(count, shift - BITS, root[subidx], tail_node)
        return root[:subidx] + (new_child,) + root[subidx + 1:]
    else:
        # New child path
        new_child = _new_path(shift - BITS, tail_node)
        return root + (new_child,)


def _assoc_node(shift, node, index, value):
    """Return a new trie node with value at index replaced."""
    if shift == 0:
        new_node = list(node)
        new_node[index & MASK] = value
        return tuple(new_node)

    subidx = (index >> shift) & MASK
    new_child = _assoc_node(shift - BITS, node[subidx], index, value)
    new_node = list(node)
    new_node[subidx] = new_child
    return tuple(new_node)


def _iter_node(node, shift):
    if shift == BITS:
        for leaf in node:
            yield from leaf
        return
    for child in node:
        yield from _iter_node(child, shift - BITS)


def _values_equal(left, right):
    return left is right or left == right
