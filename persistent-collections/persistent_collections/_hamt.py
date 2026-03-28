"""Pure-Python HAMT (Hash Array Mapped Trie) implementation.

Provides O(log32 n) structural-sharing persistent map operations.
Algorithm mirrors CPython's internal Python/hamt.c.
"""

from __future__ import annotations

from typing import Any, cast

BITS_PER_LEVEL = 5
BRANCH_FACTOR = 1 << BITS_PER_LEVEL  # 32
MASK = BRANCH_FACTOR - 1
MAX_DEPTH = 7  # 32-bit hash / 5 bits = ~7 levels

# ArrayNode promotion threshold (matches C implementation)
_ARRAY_NODE_THRESHOLD = 16

LeafEntry = tuple[Any, Any]
ArraySlot = Any
Node = Any


def _popcount(x: int) -> int:
    """Count set bits in integer."""
    return x.bit_count()


def _hash_fold(h: int) -> int:
    """Fold a Python hash into 32 bits using XOR, matching C implementation."""
    h = h & 0xFFFFFFFFFFFFFFFF  # Ensure positive for bit ops
    return (h & 0xFFFFFFFF) ^ ((h >> 32) & 0xFFFFFFFF)


def _keys_equal(left: Any, right: Any) -> bool:
    """Match Python mapping semantics for same-object non-reflexive keys."""
    return left is right or left == right


class _ArrayNode:
    """Dense HAMT node with 32 slots, used when a BitmapNode has >16 children.

    Each slot is either None (empty) or a subnode/_BitmapNode.
    This avoids the overhead of bitmap indexing for dense nodes.
    """
    __slots__ = ('array', 'count')

    def __init__(self, count: int, array: list[ArraySlot]) -> None:
        self.count = count  # Number of non-None entries
        self.array = array  # list of 32 entries (None or (key, val) or subnode)

    def find(self, shift: int, hash_val: int, key: Any) -> Any:
        idx = (hash_val >> shift) & MASK
        entry = self.array[idx]
        if entry is None:
            raise KeyError(key)
        if isinstance(entry, tuple):
            # Leaf entry: (key, value)
            if _keys_equal(entry[0], key):
                return entry[1]
            raise KeyError(key)
        # Subnode
        return entry.find(shift + BITS_PER_LEVEL, hash_val, key)

    def assoc(self, shift: int, hash_val: int, key: Any, value: Any) -> tuple[_ArrayNode, bool]:
        idx = (hash_val >> shift) & MASK
        entry = self.array[idx]

        if entry is None:
            # Empty slot — insert leaf
            new_array = list(self.array)
            new_array[idx] = (key, value)
            return _ArrayNode(self.count + 1, new_array), True

        if isinstance(entry, tuple):
            existing_key, existing_val = entry
            if _keys_equal(existing_key, key):
                if existing_val is value:
                    return self, False
                new_array = list(self.array)
                new_array[idx] = (key, value)
                return _ArrayNode(self.count, new_array), False
            # Collision at this slot — create subnode
            existing_hash = _hash_fold(hash(existing_key))
            subnode = _create_node(
                shift + BITS_PER_LEVEL,
                existing_hash, existing_key, existing_val,
                hash_val, key, value,
            )
            new_array = list(self.array)
            new_array[idx] = subnode
            return _ArrayNode(self.count, new_array), True

        # Subnode — recurse
        new_node, added = entry.assoc(shift + BITS_PER_LEVEL, hash_val, key, value)
        if new_node is entry:
            return self, False
        new_array = list(self.array)
        new_array[idx] = new_node
        return _ArrayNode(self.count, new_array), added

    def without(self, shift: int, hash_val: int, key: Any) -> _ArrayNode | _BitmapNode | None:
        idx = (hash_val >> shift) & MASK
        entry = self.array[idx]

        if entry is None:
            raise KeyError(key)

        if isinstance(entry, tuple):
            if not _keys_equal(entry[0], key):
                raise KeyError(key)
            # Remove this leaf
            new_count = self.count - 1
            if new_count < _ARRAY_NODE_THRESHOLD:
                return self._pack(idx)
            new_array = list(self.array)
            new_array[idx] = None
            return _ArrayNode(new_count, new_array)

        # Subnode — recurse
        new_node = entry.without(shift + BITS_PER_LEVEL, hash_val, key)
        if new_node is entry:
            return self
        if new_node is None:
            new_count = self.count - 1
            if new_count < _ARRAY_NODE_THRESHOLD:
                return self._pack(idx)
            new_array = list(self.array)
            new_array[idx] = None
            return _ArrayNode(new_count, new_array)
        new_array = list(self.array)
        new_array[idx] = new_node
        return _ArrayNode(self.count, new_array)

    def _pack(self, exclude_idx: int) -> _BitmapNode:
        """Pack back into a BitmapNode when count drops below threshold."""
        new_array: list[Any] = []
        bitmap = 0
        for i in range(BRANCH_FACTOR):
            if i == exclude_idx:
                continue
            entry = self.array[i]
            if entry is not None:
                bitmap |= (1 << i)
                if isinstance(entry, tuple):
                    new_array.extend(entry)  # key, value
                else:
                    new_array.extend((None, entry))  # subnode
        return _BitmapNode(bitmap, tuple(new_array))

    def items(self) -> Any:
        for entry in self.array:
            if entry is None:
                continue
            if isinstance(entry, tuple):
                yield entry
            else:
                yield from entry.items()


class _BitmapNode:
    """Sparse HAMT node using bitmap for indexing."""
    __slots__ = ('bitmap', 'array')

    def __init__(self, bitmap: int, array: tuple[Any, ...]) -> None:
        self.bitmap = bitmap
        self.array = array  # Alternating key, value or key, subnode pairs

    def find(self, shift: int, hash_val: int, key: Any) -> Any:
        bit = 1 << ((hash_val >> shift) & MASK)
        if not (self.bitmap & bit):
            raise KeyError(key)
        idx = _popcount(self.bitmap & (bit - 1))
        key_or_none = self.array[2 * idx]
        val_or_node = self.array[2 * idx + 1]
        if key_or_none is None:
            # Subnode
            return val_or_node.find(shift + BITS_PER_LEVEL, hash_val, key)
        if _keys_equal(key_or_none, key):
            return val_or_node
        raise KeyError(key)

    def assoc(self, shift: int, hash_val: int, key: Any, value: Any) -> tuple[_BitmapNode | _ArrayNode, bool]:
        bit = 1 << ((hash_val >> shift) & MASK)
        idx = _popcount(self.bitmap & (bit - 1))

        if self.bitmap & bit:
            # Slot exists
            key_or_none = self.array[2 * idx]
            val_or_node = self.array[2 * idx + 1]

            if key_or_none is None:
                # Subnode — recurse
                new_node, added = val_or_node.assoc(shift + BITS_PER_LEVEL, hash_val, key, value)
                if new_node is val_or_node:
                    return self, False
                new_array = list(self.array)
                new_array[2 * idx + 1] = new_node
                return _BitmapNode(self.bitmap, tuple(new_array)), added

            if _keys_equal(key_or_none, key):
                # Same key — update value
                if val_or_node is value:
                    return self, False
                new_array = list(self.array)
                new_array[2 * idx + 1] = value
                return _BitmapNode(self.bitmap, tuple(new_array)), False

            # Hash collision at this level — create subnode
            existing_hash = _hash_fold(hash(key_or_none))
            new_node = _create_node(
                shift + BITS_PER_LEVEL,
                existing_hash, key_or_none, val_or_node,
                hash_val, key, value,
            )
            new_array = list(self.array)
            new_array[2 * idx] = None
            new_array[2 * idx + 1] = new_node
            return _BitmapNode(self.bitmap, tuple(new_array)), True

        else:
            # New slot
            n = _popcount(self.bitmap)
            if n >= _ARRAY_NODE_THRESHOLD:
                # Promote to ArrayNode
                return self._promote_to_array_node(shift, bit, idx, key, value, hash_val)

            new_array = list(self.array)
            new_array[2 * idx:2 * idx] = [key, value]
            return _BitmapNode(self.bitmap | bit, tuple(new_array)), True

    def _promote_to_array_node(
        self,
        shift: int,
        new_bit: int,
        new_idx: int,
        key: Any,
        value: Any,
        hash_val: int,
    ) -> tuple[_ArrayNode, bool]:
        """Promote this BitmapNode to an ArrayNode when it exceeds threshold."""
        del new_bit, new_idx
        array: list[ArraySlot] = [None] * BRANCH_FACTOR
        j = 0
        for i in range(BRANCH_FACTOR):
            if self.bitmap & (1 << i):
                k = self.array[2 * j]
                v = self.array[2 * j + 1]
                if k is None:
                    # Subnode
                    array[i] = v
                else:
                    array[i] = (k, v)
                j += 1
        # Insert the new key
        slot = (hash_val >> shift) & MASK
        array[slot] = (key, value)
        count = _popcount(self.bitmap) + 1
        return _ArrayNode(count, array), True

    def without(self, shift: int, hash_val: int, key: Any) -> _BitmapNode | None:
        bit = 1 << ((hash_val >> shift) & MASK)
        if not (self.bitmap & bit):
            raise KeyError(key)
        idx = _popcount(self.bitmap & (bit - 1))
        key_or_none = self.array[2 * idx]
        val_or_node = self.array[2 * idx + 1]

        if key_or_none is None:
            # Subnode
            new_node = val_or_node.without(shift + BITS_PER_LEVEL, hash_val, key)
            if new_node is val_or_node:
                return self
            if new_node is not None:
                new_array = list(self.array)
                new_array[2 * idx + 1] = new_node
                return _BitmapNode(self.bitmap, tuple(new_array))
            # Subnode became empty
            if self.bitmap == bit:
                return None
            new_array = list(self.array)
            del new_array[2 * idx:2 * idx + 2]
            return _BitmapNode(self.bitmap ^ bit, tuple(new_array))

        if _keys_equal(key_or_none, key):
            if self.bitmap == bit:
                return None
            new_array = list(self.array)
            del new_array[2 * idx:2 * idx + 2]
            return _BitmapNode(self.bitmap ^ bit, tuple(new_array))

        raise KeyError(key)

    def items(self) -> Any:
        for i in range(0, len(self.array), 2):
            key_or_none = self.array[i]
            val_or_node = self.array[i + 1]
            if key_or_none is None:
                yield from val_or_node.items()
            else:
                yield (key_or_none, val_or_node)


EMPTY_BITMAP_NODE = _BitmapNode(0, ())


def _create_node(
    shift: int,
    hash1: int,
    key1: Any,
    val1: Any,
    hash2: int,
    key2: Any,
    val2: Any,
) -> Node:
    """Create a node that contains two key-value pairs."""
    if shift >= 32:
        # Hash collision — store both in a collision node
        return _CollisionNode(hash1, ((key1, val1), (key2, val2)))

    idx1 = (hash1 >> shift) & MASK
    idx2 = (hash2 >> shift) & MASK

    if idx1 == idx2:
        subnode = _create_node(shift + BITS_PER_LEVEL, hash1, key1, val1, hash2, key2, val2)
        return _BitmapNode(1 << idx1, (None, subnode))

    bit1 = 1 << idx1
    bit2 = 1 << idx2
    if idx1 < idx2:
        return _BitmapNode(bit1 | bit2, (key1, val1, key2, val2))
    else:
        return _BitmapNode(bit1 | bit2, (key2, val2, key1, val1))


class _CollisionNode:
    """Handles hash collisions by storing multiple key-value pairs."""
    __slots__ = ('hash_val', 'pairs')

    def __init__(self, hash_val: int, pairs: tuple[LeafEntry, ...]) -> None:
        self.hash_val = hash_val
        self.pairs = pairs  # tuple of (key, value) tuples

    def find(self, shift: int, hash_val: int, key: Any) -> Any:
        del shift, hash_val
        for k, v in self.pairs:
            if _keys_equal(k, key):
                return v
        raise KeyError(key)

    def assoc(self, shift: int, hash_val: int, key: Any, value: Any) -> tuple[Node, bool]:
        if hash_val == self.hash_val:
            for i, (k, v) in enumerate(self.pairs):
                if _keys_equal(k, key):
                    if v is value:
                        return self, False
                    new_pairs = list(self.pairs)
                    new_pairs[i] = (key, value)
                    return _CollisionNode(self.hash_val, tuple(new_pairs)), False
            return _CollisionNode(self.hash_val, self.pairs + ((key, value),)), True
        # Different hash — need to elevate to bitmap node
        node: Node = _BitmapNode(0, ())
        for k, v in self.pairs:
            node, _ = node.assoc(shift, self.hash_val & 0xFFFFFFFF, k, v)
        return cast(tuple[Node, bool], node.assoc(shift, hash_val, key, value))

    def without(self, shift: int, hash_val: int, key: Any) -> _CollisionNode | _BitmapNode | None:
        new_pairs = tuple((k, v) for k, v in self.pairs if not _keys_equal(k, key))
        if len(new_pairs) == len(self.pairs):
            raise KeyError(key)
        if len(new_pairs) == 0:
            return None
        if len(new_pairs) == 1:
            k, v = new_pairs[0]
            return _BitmapNode(1 << ((hash_val >> shift) & MASK), (k, v))
        return _CollisionNode(self.hash_val, new_pairs)

    def items(self) -> Any:
        yield from self.pairs
