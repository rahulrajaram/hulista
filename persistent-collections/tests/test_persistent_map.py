"""Comprehensive tests for PersistentMap."""
import pytest
import collections.abc

from persistent_collections import PersistentMap


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_empty(self):
        m = PersistentMap()
        assert len(m) == 0

    def test_kwargs(self):
        m = PersistentMap(a=1, b=2, c=3)
        assert len(m) == 3
        assert m['a'] == 1
        assert m['b'] == 2
        assert m['c'] == 3

    def test_from_dict_empty(self):
        m = PersistentMap.from_dict({})
        assert len(m) == 0

    def test_from_dict_single(self):
        m = PersistentMap.from_dict({'x': 42})
        assert len(m) == 1
        assert m['x'] == 42

    def test_from_dict_multiple(self):
        d = {'a': 1, 'b': 2, 'c': 3, 'd': 4}
        m = PersistentMap.from_dict(d)
        assert len(m) == len(d)
        for k, v in d.items():
            assert m[k] == v

    def test_is_mapping(self):
        m = PersistentMap()
        assert isinstance(m, collections.abc.Mapping)


# ---------------------------------------------------------------------------
# set() — structural sharing
# ---------------------------------------------------------------------------

class TestSet:
    def test_set_returns_new_map(self):
        m1 = PersistentMap()
        m2 = m1.set('key', 'val')
        assert m1 is not m2
        assert len(m1) == 0
        assert len(m2) == 1

    def test_set_original_unchanged(self):
        m1 = PersistentMap.from_dict({'a': 1})
        m2 = m1.set('b', 2)
        assert 'b' not in m1
        assert 'b' in m2

    def test_set_increments_count(self):
        m = PersistentMap()
        for i in range(10):
            m = m.set(f'k{i}', i)
        assert len(m) == 10

    def test_set_replace_does_not_increment_count(self):
        m1 = PersistentMap.from_dict({'a': 1})
        m2 = m1.set('a', 99)
        assert len(m2) == 1
        assert m2['a'] == 99

    def test_set_same_value_identity_returns_self(self):
        sentinel = object()
        m1 = PersistentMap().set('k', sentinel)
        m2 = m1.set('k', sentinel)
        # Should return the same map (no-op optimization)
        assert m2 is m1

    def test_set_shares_structure(self):
        """After a set, the old map still works correctly."""
        base = PersistentMap.from_dict({str(i): i for i in range(50)})
        updated = base.set('999', 999)
        # All original keys still accessible on base
        for i in range(50):
            assert base[str(i)] == i
        # New key on updated
        assert updated['999'] == 999
        # Original keys also accessible on updated
        for i in range(50):
            assert updated[str(i)] == i

    def test_set_integer_keys(self):
        m = PersistentMap()
        for i in range(100):
            m = m.set(i, i * 2)
        for i in range(100):
            assert m[i] == i * 2

    def test_set_tuple_keys(self):
        m = PersistentMap()
        m = m.set((1, 2), 'a')
        m = m.set((3, 4), 'b')
        assert m[(1, 2)] == 'a'
        assert m[(3, 4)] == 'b'


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_returns_new_map(self):
        m1 = PersistentMap.from_dict({'a': 1, 'b': 2})
        m2 = m1.delete('a')
        assert m1 is not m2

    def test_delete_original_unchanged(self):
        m1 = PersistentMap.from_dict({'a': 1, 'b': 2})
        m2 = m1.delete('a')
        assert 'a' in m1
        assert 'a' not in m2

    def test_delete_decrements_count(self):
        m = PersistentMap.from_dict({'a': 1, 'b': 2, 'c': 3})
        m2 = m.delete('b')
        assert len(m2) == 2

    def test_delete_missing_key_raises(self):
        m = PersistentMap.from_dict({'a': 1})
        with pytest.raises(KeyError):
            m.delete('z')

    def test_delete_last_key(self):
        m = PersistentMap.from_dict({'a': 1})
        m2 = m.delete('a')
        assert len(m2) == 0
        assert 'a' not in m2

    def test_delete_all_keys(self):
        keys = list(range(20))
        m = PersistentMap.from_dict({k: k for k in keys})
        for k in keys:
            m = m.delete(k)
        assert len(m) == 0

    def test_delete_then_reinsert(self):
        m = PersistentMap.from_dict({'a': 1, 'b': 2})
        m2 = m.delete('a').set('a', 99)
        assert m2['a'] == 99
        assert m['a'] == 1  # Original unaffected


# ---------------------------------------------------------------------------
# get / __getitem__ / __contains__
# ---------------------------------------------------------------------------

class TestLookup:
    def test_getitem_present(self):
        m = PersistentMap.from_dict({'hello': 'world'})
        assert m['hello'] == 'world'

    def test_getitem_missing_raises(self):
        m = PersistentMap()
        with pytest.raises(KeyError):
            _ = m['missing']

    def test_get_present(self):
        m = PersistentMap.from_dict({'x': 10})
        assert m.get('x') == 10

    def test_get_missing_default_none(self):
        m = PersistentMap()
        assert m.get('nope') is None

    def test_get_missing_custom_default(self):
        m = PersistentMap()
        assert m.get('nope', 42) == 42

    def test_contains_present(self):
        m = PersistentMap.from_dict({'a': 1})
        assert 'a' in m

    def test_contains_absent(self):
        m = PersistentMap.from_dict({'a': 1})
        assert 'b' not in m

    def test_contains_empty(self):
        m = PersistentMap()
        assert 'anything' not in m


# ---------------------------------------------------------------------------
# __len__
# ---------------------------------------------------------------------------

class TestLen:
    def test_empty_len(self):
        assert len(PersistentMap()) == 0

    def test_len_after_inserts(self):
        m = PersistentMap()
        for i in range(50):
            m = m.set(i, i)
        assert len(m) == 50

    def test_len_after_deletes(self):
        m = PersistentMap.from_dict({i: i for i in range(10)})
        m = m.delete(0).delete(1).delete(2)
        assert len(m) == 7


# ---------------------------------------------------------------------------
# Iteration
# ---------------------------------------------------------------------------

class TestIteration:
    def test_iter_keys(self):
        d = {'a': 1, 'b': 2, 'c': 3}
        m = PersistentMap.from_dict(d)
        assert set(m) == set(d.keys())

    def test_keys(self):
        d = {'x': 10, 'y': 20}
        m = PersistentMap.from_dict(d)
        assert set(m.keys()) == set(d.keys())

    def test_values(self):
        d = {'x': 10, 'y': 20}
        m = PersistentMap.from_dict(d)
        assert set(m.values()) == set(d.values())

    def test_items(self):
        d = {'x': 10, 'y': 20, 'z': 30}
        m = PersistentMap.from_dict(d)
        assert set(m.items()) == set(d.items())

    def test_iter_empty(self):
        m = PersistentMap()
        assert list(m) == []

    def test_iter_large(self):
        d = {f'k{i}': i for i in range(200)}
        m = PersistentMap.from_dict(d)
        assert set(m.items()) == set(d.items())

    def test_iter_count_matches_len(self):
        d = {i: i * 2 for i in range(75)}
        m = PersistentMap.from_dict(d)
        assert sum(1 for _ in m) == len(m)


# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------

class TestHash:
    def test_hashable(self):
        m = PersistentMap.from_dict({'a': 1, 'b': 2})
        h = hash(m)
        assert isinstance(h, int)

    def test_empty_hashable(self):
        m = PersistentMap()
        h = hash(m)
        assert isinstance(h, int)

    def test_hash_stable(self):
        m = PersistentMap.from_dict({'a': 1})
        assert hash(m) == hash(m)

    def test_equal_maps_same_hash(self):
        m1 = PersistentMap.from_dict({'a': 1, 'b': 2})
        m2 = PersistentMap.from_dict({'b': 2, 'a': 1})
        assert m1 == m2
        assert hash(m1) == hash(m2)

    def test_usable_as_dict_key(self):
        m1 = PersistentMap.from_dict({'x': 1})
        m2 = PersistentMap.from_dict({'y': 2})
        d = {m1: 'first', m2: 'second'}
        assert d[m1] == 'first'
        assert d[m2] == 'second'

    def test_usable_in_set(self):
        m1 = PersistentMap.from_dict({'a': 1})
        m2 = PersistentMap.from_dict({'a': 1})  # Equal but distinct objects
        m3 = PersistentMap.from_dict({'b': 2})
        s = {m1, m2, m3}
        assert len(s) == 2  # m1 and m2 are equal


# ---------------------------------------------------------------------------
# Equality
# ---------------------------------------------------------------------------

class TestEquality:
    def test_equal_persistent_maps(self):
        m1 = PersistentMap.from_dict({'a': 1, 'b': 2})
        m2 = PersistentMap.from_dict({'a': 1, 'b': 2})
        assert m1 == m2

    def test_unequal_different_keys(self):
        m1 = PersistentMap.from_dict({'a': 1})
        m2 = PersistentMap.from_dict({'b': 1})
        assert m1 != m2

    def test_unequal_different_values(self):
        m1 = PersistentMap.from_dict({'a': 1})
        m2 = PersistentMap.from_dict({'a': 2})
        assert m1 != m2

    def test_unequal_different_sizes(self):
        m1 = PersistentMap.from_dict({'a': 1, 'b': 2})
        m2 = PersistentMap.from_dict({'a': 1})
        assert m1 != m2

    def test_equal_to_plain_dict(self):
        d = {'a': 1, 'b': 2, 'c': 3}
        m = PersistentMap.from_dict(d)
        assert m == d

    def test_not_equal_to_different_dict(self):
        m = PersistentMap.from_dict({'a': 1})
        assert m != {'a': 2}

    def test_empty_maps_equal(self):
        assert PersistentMap() == PersistentMap()

    def test_same_root_identity_fast_path(self):
        m1 = PersistentMap.from_dict({'a': 1})
        m2 = m1.set('b', 2).delete('b')
        # m2 may or may not share root with m1, but values should be equal
        assert m1 == m2

    def test_not_equal_to_non_mapping(self):
        m = PersistentMap.from_dict({'a': 1})
        result = m.__eq__([1, 2, 3])
        assert result is NotImplemented


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_setattr_raises(self):
        m = PersistentMap()
        with pytest.raises(AttributeError, match="immutable"):
            m.foo = 'bar'

    def test_delattr_raises(self):
        m = PersistentMap()
        with pytest.raises(AttributeError, match="immutable"):
            del m._root

    def test_no_item_assignment(self):
        m = PersistentMap()
        with pytest.raises((AttributeError, TypeError)):
            m['key'] = 'value'  # Mapping ABC does not support item assignment

    def test_set_does_not_mutate_original(self):
        m1 = PersistentMap.from_dict({'a': 1})
        m2 = m1.set('b', 2)
        assert len(m1) == 1
        assert 'b' not in m1

    def test_delete_does_not_mutate_original(self):
        m1 = PersistentMap.from_dict({'a': 1, 'b': 2})
        m2 = m1.delete('a')
        assert 'a' in m1
        assert len(m1) == 2


# ---------------------------------------------------------------------------
# Large map operations
# ---------------------------------------------------------------------------

class TestLargeMap:
    def test_insert_100_keys(self):
        m = PersistentMap()
        for i in range(100):
            m = m.set(f'key_{i}', i)
        assert len(m) == 100
        for i in range(100):
            assert m[f'key_{i}'] == i

    def test_delete_50_of_100_keys(self):
        m = PersistentMap.from_dict({f'k{i}': i for i in range(100)})
        for i in range(0, 100, 2):
            m = m.delete(f'k{i}')
        assert len(m) == 50
        for i in range(1, 100, 2):
            assert m[f'k{i}'] == i

    def test_update_all_values(self):
        m = PersistentMap.from_dict({i: i for i in range(100)})
        m2 = m
        for i in range(100):
            m2 = m2.set(i, i * 10)
        assert len(m2) == 100
        for i in range(100):
            assert m2[i] == i * 10
        # Original unchanged
        for i in range(100):
            assert m[i] == i

    def test_integer_keys_no_collision(self):
        """Integer keys 0..127 have hash == value, exercising many trie branches."""
        m = PersistentMap()
        for i in range(128):
            m = m.set(i, i)
        assert len(m) == 128
        for i in range(128):
            assert m[i] == i

    def test_from_dict_500_keys(self):
        d = {f'item_{i}': i * 3 for i in range(500)}
        m = PersistentMap.from_dict(d)
        assert len(m) == 500
        for k, v in d.items():
            assert m[k] == v


# ---------------------------------------------------------------------------
# Stress test — structural sharing
# ---------------------------------------------------------------------------

class TestStructuralSharingStress:
    def test_1000_sequential_sets(self):
        """Build a chain of 1000 maps; all should remain valid."""
        versions = [PersistentMap()]
        for i in range(1000):
            versions.append(versions[-1].set(f'k{i}', i))

        # Each version i has exactly i+1 keys
        for i, m in enumerate(versions):
            assert len(m) == i, f"Version {i} should have {i} keys, got {len(m)}"

        # Final version contains all keys
        final = versions[-1]
        for i in range(1000):
            assert final[f'k{i}'] == i

    def test_forking_versions(self):
        """Fork a map and ensure independent evolution."""
        base = PersistentMap.from_dict({i: i for i in range(50)})
        branch_a = base
        branch_b = base
        for i in range(50, 100):
            branch_a = branch_a.set(i, f'A{i}')
        for i in range(50, 100):
            branch_b = branch_b.set(i, f'B{i}')

        # base still has 50 keys
        assert len(base) == 50
        # Each branch has 100 keys
        assert len(branch_a) == 100
        assert len(branch_b) == 100
        # Branches diverge
        for i in range(50, 100):
            assert branch_a[i] == f'A{i}'
            assert branch_b[i] == f'B{i}'

    def test_alternating_set_delete(self):
        """Alternate set/delete to stress the trie restructuring."""
        m = PersistentMap()
        for i in range(200):
            m = m.set(i, i)
        for i in range(0, 200, 3):
            m = m.delete(i)
        expected_keys = {i for i in range(200) if i % 3 != 0}
        assert len(m) == len(expected_keys)
        for k in expected_keys:
            assert m[k] == k


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr_empty(self):
        assert repr(PersistentMap()) == 'PersistentMap({})'

    def test_repr_single(self):
        m = PersistentMap().set('a', 1)
        assert repr(m) == "PersistentMap({'a': 1})"

    def test_repr_contains_all_items(self):
        d = {'x': 10, 'y': 20}
        m = PersistentMap.from_dict(d)
        r = repr(m)
        assert 'PersistentMap(' in r
        assert "'x': 10" in r
        assert "'y': 20" in r
