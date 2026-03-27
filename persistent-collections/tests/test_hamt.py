"""Unit tests for the internal HAMT nodes."""
import pytest

from persistent_collections._hamt import (
    _BitmapNode,
    _CollisionNode,
    _ArrayNode,
    _create_node,
    _popcount,
    _hash_fold,
    EMPTY_BITMAP_NODE,
    BITS_PER_LEVEL,
    BRANCH_FACTOR,
    MASK,
    _ARRAY_NODE_THRESHOLD,
)


class TestPopcount:
    def test_zero(self):
        assert _popcount(0) == 0

    def test_one(self):
        assert _popcount(1) == 1

    def test_all_ones(self):
        # 32-bit all-ones
        assert _popcount(0xFFFFFFFF) == 32

    def test_alternating(self):
        assert _popcount(0b10101010) == 4

    def test_single_bit(self):
        for i in range(32):
            assert _popcount(1 << i) == 1


class TestHashFold:
    def test_small_positive(self):
        # Small integers should remain unchanged (upper 32 bits are zero)
        assert _hash_fold(42) == 42

    def test_negative_hash(self):
        # Should produce a 32-bit result
        result = _hash_fold(-1)
        assert 0 <= result < 2**32

    def test_large_value(self):
        result = _hash_fold(0x1234567890ABCDEF)
        assert 0 <= result < 2**32


class TestConstants:
    def test_branch_factor(self):
        assert BRANCH_FACTOR == 32

    def test_mask(self):
        assert MASK == 31

    def test_bits_per_level(self):
        assert BITS_PER_LEVEL == 5


class TestEmptyBitmapNode:
    def test_find_raises(self):
        with pytest.raises(KeyError):
            EMPTY_BITMAP_NODE.find(0, 0, 'x')

    def test_items_empty(self):
        assert list(EMPTY_BITMAP_NODE.items()) == []

    def test_assoc_returns_new_node(self):
        node, added = EMPTY_BITMAP_NODE.assoc(0, _hash_fold(hash('a')), 'a', 1)
        assert node is not EMPTY_BITMAP_NODE
        assert added is True
        assert node.find(0, _hash_fold(hash('a')), 'a') == 1


class TestBitmapNodeAssoc:
    def test_insert_single(self):
        h = _hash_fold(hash('key'))
        node, added = EMPTY_BITMAP_NODE.assoc(0, h, 'key', 'val')
        assert added is True
        assert node.find(0, h, 'key') == 'val'

    def test_insert_two_different_hashes(self):
        h1 = _hash_fold(hash('alpha'))
        h2 = _hash_fold(hash('beta'))
        node, _ = EMPTY_BITMAP_NODE.assoc(0, h1, 'alpha', 1)
        node, _ = node.assoc(0, h2, 'beta', 2)
        assert node.find(0, h1, 'alpha') == 1
        assert node.find(0, h2, 'beta') == 2

    def test_update_existing_key(self):
        h = _hash_fold(hash('k'))
        node, _ = EMPTY_BITMAP_NODE.assoc(0, h, 'k', 100)
        node2, added = node.assoc(0, h, 'k', 200)
        assert added is False
        assert node2.find(0, h, 'k') == 200
        # Old node unchanged
        assert node.find(0, h, 'k') == 100

    def test_same_value_identity_noop(self):
        sentinel = object()
        h = _hash_fold(hash('k'))
        node, _ = EMPTY_BITMAP_NODE.assoc(0, h, 'k', sentinel)
        node2, added = node.assoc(0, h, 'k', sentinel)
        assert node2 is node
        assert added is False

    def test_items_single(self):
        h = _hash_fold(hash('x'))
        node, _ = EMPTY_BITMAP_NODE.assoc(0, h, 'x', 99)
        assert list(node.items()) == [('x', 99)]

    def test_items_multiple(self):
        node = EMPTY_BITMAP_NODE
        keys = ['alpha', 'beta', 'gamma', 'delta']
        for i, k in enumerate(keys):
            node, _ = node.assoc(0, _hash_fold(hash(k)), k, i)
        items = dict(node.items())
        for i, k in enumerate(keys):
            assert items[k] == i

    def test_collision_at_same_index_creates_subnode(self):
        """Force two keys to share the same top-level trie index.

        Use integer keys so that hash(key) == key (CPython small-int guarantee),
        making the hash we pass to assoc() consistent with what _create_node
        will recompute from the stored key.

        1  == 0b00000001: low-5 bits = 1 (trie index at shift=0 is 1)
        33 == 0b00100001: low-5 bits = 1 (same trie index at shift=0)
                          bits 5-9  = 1 (different index at shift=5 => resolves)
        """
        h1, k1 = 1, 1    # hash(1) == 1
        h2, k2 = 33, 33  # hash(33) == 33; low-5 bits identical to h1
        node, _ = EMPTY_BITMAP_NODE.assoc(0, h1, k1, 'v1')
        node2, _ = node.assoc(0, h2, k2, 'v2')
        assert node2.find(0, h1, k1) == 'v1'
        assert node2.find(0, h2, k2) == 'v2'


class TestBitmapNodeWithout:
    def test_remove_only_key(self):
        h = _hash_fold(hash('a'))
        node, _ = EMPTY_BITMAP_NODE.assoc(0, h, 'a', 1)
        result = node.without(0, h, 'a')
        assert result is None

    def test_remove_one_of_two_keys(self):
        h1 = _hash_fold(hash('a'))
        h2 = _hash_fold(hash('b'))
        node, _ = EMPTY_BITMAP_NODE.assoc(0, h1, 'a', 1)
        node, _ = node.assoc(0, h2, 'b', 2)
        node2 = node.without(0, h1, 'a')
        assert node2 is not None
        with pytest.raises(KeyError):
            node2.find(0, h1, 'a')
        assert node2.find(0, h2, 'b') == 2
        # Original unchanged
        assert node.find(0, h1, 'a') == 1

    def test_remove_missing_key_raises(self):
        h = _hash_fold(hash('x'))
        with pytest.raises(KeyError):
            EMPTY_BITMAP_NODE.without(0, h, 'x')

    def test_remove_from_subnode(self):
        """Force keys into a subnode (via index collision at shift=0) then remove one.

        Use integer keys so hash(key) == key (CPython small-int guarantee).
        1  and 33 share the same low-5 bits (trie index 1 at shift=0) but
        differ at shift=5, so they nest into a subnode without becoming a
        _CollisionNode.
        """
        h1, k1 = 1, 1
        h2, k2 = 33, 33
        node, _ = EMPTY_BITMAP_NODE.assoc(0, h1, k1, 'v1')
        node, _ = node.assoc(0, h2, k2, 'v2')
        node2 = node.without(0, h1, k1)
        with pytest.raises(KeyError):
            node2.find(0, h1, k1)
        assert node2.find(0, h2, k2) == 'v2'


class TestArrayNode:
    """Test ArrayNode promotion and operations."""

    def test_promote_from_bitmap(self):
        """Adding > 16 children to a BitmapNode should promote to ArrayNode."""
        node = EMPTY_BITMAP_NODE
        # Insert keys that map to different trie indices at shift=0
        for i in range(20):
            node, _ = node.assoc(0, i, i, f'v{i}')
        # After 16+ children, should have promoted to ArrayNode
        assert isinstance(node, _ArrayNode)
        # Verify all entries
        for i in range(20):
            assert node.find(0, i, i) == f'v{i}'

    def test_array_node_remove_demotes(self):
        """Removing entries from an ArrayNode should demote back when below threshold."""
        node = EMPTY_BITMAP_NODE
        for i in range(20):
            node, _ = node.assoc(0, i, i, f'v{i}')
        assert isinstance(node, _ArrayNode)
        # Remove entries to get below threshold
        for i in range(6):
            node = node.without(0, i, i)
        # Should have demoted back to BitmapNode
        assert isinstance(node, _BitmapNode)

    def test_array_node_items(self):
        node = EMPTY_BITMAP_NODE
        for i in range(20):
            node, _ = node.assoc(0, i, i, f'v{i}')
        items = dict(node.items())
        for i in range(20):
            assert items[i] == f'v{i}'


class TestCreateNode:
    def test_different_top_level_indices(self):
        """Keys that differ at shift=0 produce a two-entry BitmapNode."""
        h1 = 0b00001  # index 1
        h2 = 0b00010  # index 2
        node = _create_node(0, h1, 'k1', 'v1', h2, 'k2', 'v2')
        assert isinstance(node, _BitmapNode)
        assert node.find(0, h1, 'k1') == 'v1'
        assert node.find(0, h2, 'k2') == 'v2'

    def test_same_top_level_index_recurses(self):
        """Keys with same index at shift=0 but different at shift=5."""
        h1 = 0b00001
        h2 = 0b100001
        node = _create_node(0, h1, 'k1', 'v1', h2, 'k2', 'v2')
        assert node.find(0, h1, 'k1') == 'v1'
        assert node.find(0, h2, 'k2') == 'v2'

    def test_full_collision_produces_collision_node(self):
        """When shift >= 32, produce a _CollisionNode."""
        node = _create_node(35, 12345, 'k1', 'v1', 12345, 'k2', 'v2')
        assert isinstance(node, _CollisionNode)


class TestCollisionNode:
    def _make(self):
        return _CollisionNode(99999, (('k1', 'v1'), ('k2', 'v2')))

    def test_find_existing(self):
        node = self._make()
        assert node.find(0, 99999, 'k1') == 'v1'
        assert node.find(0, 99999, 'k2') == 'v2'

    def test_find_missing_raises(self):
        node = self._make()
        with pytest.raises(KeyError):
            node.find(0, 99999, 'k3')

    def test_assoc_new_key_same_hash(self):
        node = self._make()
        node2, added = node.assoc(0, 99999, 'k3', 'v3')
        assert added is True
        assert isinstance(node2, _CollisionNode)
        assert node2.find(0, 99999, 'k3') == 'v3'
        # Original unchanged
        with pytest.raises(KeyError):
            node.find(0, 99999, 'k3')

    def test_assoc_update_existing_same_hash(self):
        node = self._make()
        node2, added = node.assoc(0, 99999, 'k1', 'NEW')
        assert added is False
        assert node2.find(0, 99999, 'k1') == 'NEW'
        assert node.find(0, 99999, 'k1') == 'v1'

    def test_assoc_same_value_noop(self):
        node = self._make()
        node2, added = node.assoc(0, 99999, 'k1', 'v1')
        assert node2 is node
        assert added is False

    def test_assoc_different_hash_elevates(self):
        """A _CollisionNode with hash 99999 should elevate to a _BitmapNode when
        a key with a genuinely different hash is inserted.

        Use integer keys so hash(key) == key (CPython small-int guarantee).
        The _CollisionNode stores (99999, 'v1') and ('also_99999', 'v2') but
        we need the *keys themselves* to hash to 99999 for the elevation path to
        work correctly.  Using integer 99999 as the key satisfies this.
        """
        # Build a collision node where both keys genuinely hash to 99999
        cnode = _CollisionNode(99999, ((99999, 'v1'), ('also_99999', 'v2')))
        # Use integer key 12345 so hash(12345)==12345 != 99999
        different_key = 12345
        node2, added = cnode.assoc(0, different_key, different_key, 'v_new')
        assert added is True
        # Should produce a BitmapNode (or ArrayNode if many)
        assert not isinstance(node2, _CollisionNode)
        assert node2.find(0, 99999, 99999) == 'v1'
        assert node2.find(0, different_key, different_key) == 'v_new'

    def test_without_one_of_two(self):
        node = self._make()
        node2 = node.without(0, 99999, 'k1')
        # Single-pair collision should simplify to BitmapNode
        assert isinstance(node2, _BitmapNode)
        assert node2.find(0, 99999, 'k2') == 'v2'

    def test_without_last_pair_returns_none(self):
        node = _CollisionNode(42, (('only', 'val'),))
        result = node.without(0, 42, 'only')
        assert result is None

    def test_without_missing_raises(self):
        node = self._make()
        with pytest.raises(KeyError):
            node.without(0, 99999, 'missing')

    def test_items(self):
        node = self._make()
        assert set(node.items()) == {('k1', 'v1'), ('k2', 'v2')}

    def test_assoc_three_pairs(self):
        node = _CollisionNode(999, (('a', 1), ('b', 2)))
        node2, added = node.assoc(0, 999, 'c', 3)
        assert added is True
        assert isinstance(node2, _CollisionNode)
        assert len(node2.pairs) == 3
        assert node2.find(0, 999, 'c') == 3

    def test_without_from_three_pairs(self):
        node = _CollisionNode(999, (('a', 1), ('b', 2), ('c', 3)))
        node2 = node.without(0, 999, 'b')
        assert isinstance(node2, _CollisionNode)
        assert len(node2.pairs) == 2
        assert node2.find(0, 999, 'a') == 1
        assert node2.find(0, 999, 'c') == 3
