"""Pure-Python HAMT (Hash Array Mapped Trie) implementation.

Provides O(log32 n) structural-sharing persistent map operations.
Algorithm mirrors CPython's internal Python/hamt.c.
"""

BITS_PER_LEVEL = 5
BRANCH_FACTOR = 1 << BITS_PER_LEVEL  # 32
MASK = BRANCH_FACTOR - 1
MAX_DEPTH = 7  # 32-bit hash / 5 bits = ~7 levels


def _popcount(x):
    """Count set bits in integer."""
    return bin(x).count('1')


class _BitmapNode:
    """Sparse HAMT node using bitmap for indexing."""
    __slots__ = ('bitmap', 'array')

    def __init__(self, bitmap, array):
        self.bitmap = bitmap
        self.array = array  # Alternating key, value or key, subnode pairs

    def find(self, shift, hash_val, key):
        bit = 1 << ((hash_val >> shift) & MASK)
        if not (self.bitmap & bit):
            raise KeyError(key)
        idx = _popcount(self.bitmap & (bit - 1))
        key_or_none = self.array[2 * idx]
        val_or_node = self.array[2 * idx + 1]
        if key_or_none is None:
            # Subnode
            return val_or_node.find(shift + BITS_PER_LEVEL, hash_val, key)
        if key_or_none == key:
            return val_or_node
        raise KeyError(key)

    def assoc(self, shift, hash_val, key, value):
        bit = 1 << ((hash_val >> shift) & MASK)
        idx = _popcount(self.bitmap & (bit - 1))

        if self.bitmap & bit:
            # Slot exists
            key_or_none = self.array[2 * idx]
            val_or_node = self.array[2 * idx + 1]

            if key_or_none is None:
                # Subnode — recurse
                new_node = val_or_node.assoc(shift + BITS_PER_LEVEL, hash_val, key, value)
                if new_node is val_or_node:
                    return self
                new_array = list(self.array)
                new_array[2 * idx + 1] = new_node
                return _BitmapNode(self.bitmap, tuple(new_array))

            if key_or_none == key:
                # Same key — update value
                if val_or_node is value:
                    return self
                new_array = list(self.array)
                new_array[2 * idx + 1] = value
                return _BitmapNode(self.bitmap, tuple(new_array))

            # Hash collision at this level — create subnode
            existing_hash = hash(key_or_none) & 0xFFFFFFFF
            new_node = _create_node(
                shift + BITS_PER_LEVEL,
                existing_hash, key_or_none, val_or_node,
                hash_val, key, value,
            )
            new_array = list(self.array)
            new_array[2 * idx] = None
            new_array[2 * idx + 1] = new_node
            return _BitmapNode(self.bitmap, tuple(new_array))

        else:
            # New slot
            new_array = list(self.array)
            new_array[2 * idx:2 * idx] = [key, value]
            return _BitmapNode(self.bitmap | bit, tuple(new_array))

    def without(self, shift, hash_val, key):
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

        if key_or_none == key:
            if self.bitmap == bit:
                return None
            new_array = list(self.array)
            del new_array[2 * idx:2 * idx + 2]
            return _BitmapNode(self.bitmap ^ bit, tuple(new_array))

        raise KeyError(key)

    def items(self):
        for i in range(0, len(self.array), 2):
            key_or_none = self.array[i]
            val_or_node = self.array[i + 1]
            if key_or_none is None:
                yield from val_or_node.items()
            else:
                yield (key_or_none, val_or_node)


EMPTY_BITMAP_NODE = _BitmapNode(0, ())


def _create_node(shift, hash1, key1, val1, hash2, key2, val2):
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

    def __init__(self, hash_val, pairs):
        self.hash_val = hash_val
        self.pairs = pairs  # tuple of (key, value) tuples

    def find(self, shift, hash_val, key):
        for k, v in self.pairs:
            if k == key:
                return v
        raise KeyError(key)

    def assoc(self, shift, hash_val, key, value):
        if hash_val == self.hash_val:
            for i, (k, v) in enumerate(self.pairs):
                if k == key:
                    if v is value:
                        return self
                    new_pairs = list(self.pairs)
                    new_pairs[i] = (key, value)
                    return _CollisionNode(self.hash_val, tuple(new_pairs))
            return _CollisionNode(self.hash_val, self.pairs + ((key, value),))
        # Different hash — need to elevate to bitmap node
        node = _BitmapNode(0, ())
        for k, v in self.pairs:
            node = node.assoc(shift, self.hash_val & 0xFFFFFFFF, k, v)
        return node.assoc(shift, hash_val, key, value)

    def without(self, shift, hash_val, key):
        new_pairs = tuple((k, v) for k, v in self.pairs if k != key)
        if len(new_pairs) == len(self.pairs):
            raise KeyError(key)
        if len(new_pairs) == 0:
            return None
        if len(new_pairs) == 1:
            k, v = new_pairs[0]
            return _BitmapNode(1 << ((hash_val >> shift) & MASK), (k, v))
        return _CollisionNode(self.hash_val, new_pairs)

    def items(self):
        yield from self.pairs
