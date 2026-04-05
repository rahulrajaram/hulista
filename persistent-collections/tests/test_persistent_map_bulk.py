"""Tests for PersistentMap bulk operations: update, merge, without_many,
to_dict, and pickle round-trip."""
from __future__ import annotations

import pickle


from persistent_collections import PersistentMap


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_from_dict(self):
        m = PersistentMap(a=1, b=2)
        m2 = m.update({'b': 20, 'c': 3})
        assert m2['b'] == 20
        assert m2['c'] == 3
        assert m2['a'] == 1

    def test_update_from_pairs(self):
        m = PersistentMap()
        m2 = m.update([('x', 10), ('y', 20)])
        assert m2['x'] == 10
        assert m2['y'] == 20

    def test_update_returns_new_map(self):
        m = PersistentMap(a=1)
        m2 = m.update({'b': 2})
        assert m is not m2

    def test_update_does_not_mutate_original(self):
        m = PersistentMap(a=1)
        m.update({'a': 99})
        assert m['a'] == 1

    def test_update_empty_mapping(self):
        m = PersistentMap(a=1)
        m2 = m.update({})
        assert m2 == m

    def test_update_empty_pairs(self):
        m = PersistentMap(a=1)
        m2 = m.update([])
        assert m2 == m

    def test_update_len_correct(self):
        m = PersistentMap()
        m2 = m.update({'a': 1, 'b': 2, 'c': 3})
        assert len(m2) == 3

    def test_update_with_persistent_map(self):
        m1 = PersistentMap(a=1)
        m2 = PersistentMap(b=2, c=3)
        result = m1.update(m2)
        assert result['a'] == 1
        assert result['b'] == 2
        assert result['c'] == 3

    def test_update_right_wins_on_collision(self):
        m = PersistentMap(key='old')
        m2 = m.update({'key': 'new'})
        assert m2['key'] == 'new'


# ---------------------------------------------------------------------------
# merge()
# ---------------------------------------------------------------------------

class TestMerge:
    def test_merge_two_disjoint_maps(self):
        m1 = PersistentMap(a=1)
        m2 = PersistentMap(b=2)
        result = m1.merge(m2)
        assert result['a'] == 1
        assert result['b'] == 2
        assert len(result) == 2

    def test_merge_right_wins(self):
        m1 = PersistentMap(k='left')
        m2 = PersistentMap(k='right')
        result = m1.merge(m2)
        assert result['k'] == 'right'

    def test_merge_returns_new_map(self):
        m1 = PersistentMap(a=1)
        m2 = PersistentMap(b=2)
        result = m1.merge(m2)
        assert result is not m1
        assert result is not m2

    def test_merge_does_not_mutate_originals(self):
        m1 = PersistentMap(a=1)
        m2 = PersistentMap(b=2)
        m1.merge(m2)
        assert 'b' not in m1
        assert 'a' not in m2

    def test_merge_with_empty_map(self):
        m1 = PersistentMap(a=1, b=2)
        m2 = PersistentMap()
        assert m1.merge(m2) == m1

    def test_merge_into_empty_map(self):
        m1 = PersistentMap()
        m2 = PersistentMap(a=1, b=2)
        result = m1.merge(m2)
        assert result['a'] == 1
        assert result['b'] == 2

    def test_merge_large_maps(self):
        m1 = PersistentMap.from_dict({i: i for i in range(100)})
        m2 = PersistentMap.from_dict({i: i * 10 for i in range(50, 150)})
        result = m1.merge(m2)
        assert len(result) == 150
        # Keys 0-49 come from m1 unchanged
        for i in range(50):
            assert result[i] == i
        # Keys 50-149 come from m2 (right wins)
        for i in range(50, 150):
            assert result[i] == i * 10


# ---------------------------------------------------------------------------
# without_many()
# ---------------------------------------------------------------------------

class TestWithoutMany:
    def test_remove_multiple_keys(self):
        m = PersistentMap.from_dict({'a': 1, 'b': 2, 'c': 3, 'd': 4})
        m2 = m.without_many(['a', 'c'])
        assert 'a' not in m2
        assert 'c' not in m2
        assert m2['b'] == 2
        assert m2['d'] == 4

    def test_remove_absent_key_ignored(self):
        m = PersistentMap(a=1)
        m2 = m.without_many(['missing', 'also_missing'])
        assert m2 == m

    def test_remove_all_keys(self):
        m = PersistentMap.from_dict({'x': 1, 'y': 2})
        m2 = m.without_many(['x', 'y'])
        assert len(m2) == 0

    def test_remove_empty_list(self):
        m = PersistentMap(a=1)
        m2 = m.without_many([])
        assert m2 == m

    def test_does_not_mutate_original(self):
        m = PersistentMap.from_dict({'a': 1, 'b': 2})
        m.without_many(['a', 'b'])
        assert 'a' in m
        assert 'b' in m

    def test_returns_new_map(self):
        m = PersistentMap(a=1)
        m2 = m.without_many(['a'])
        assert m is not m2

    def test_mixed_present_and_absent_keys(self):
        m = PersistentMap.from_dict({'a': 1, 'b': 2, 'c': 3})
        m2 = m.without_many(['a', 'missing', 'c'])
        assert 'a' not in m2
        assert 'c' not in m2
        assert m2['b'] == 2
        assert len(m2) == 1


# ---------------------------------------------------------------------------
# to_dict() / from_dict() round-trip
# ---------------------------------------------------------------------------

class TestToDictFromDict:
    def test_to_dict_empty(self):
        assert PersistentMap().to_dict() == {}

    def test_to_dict_preserves_all_pairs(self):
        d = {'a': 1, 'b': 2, 'c': 3}
        m = PersistentMap.from_dict(d)
        assert m.to_dict() == d

    def test_from_dict_round_trip(self):
        d = {f'k{i}': i for i in range(50)}
        m = PersistentMap.from_dict(d)
        assert m.to_dict() == d

    def test_to_dict_returns_plain_dict(self):
        m = PersistentMap(a=1)
        assert type(m.to_dict()) is dict


# ---------------------------------------------------------------------------
# Pickle round-trip
# ---------------------------------------------------------------------------

class TestPickle:
    def test_pickle_empty(self):
        m = PersistentMap()
        m2 = pickle.loads(pickle.dumps(m))
        assert m == m2
        assert len(m2) == 0

    def test_pickle_with_values(self):
        m = PersistentMap.from_dict({'a': 1, 'b': 2, 'c': 3})
        m2 = pickle.loads(pickle.dumps(m))
        assert m == m2

    def test_pickle_large_map(self):
        d = {f'key_{i}': i * 2 for i in range(200)}
        m = PersistentMap.from_dict(d)
        m2 = pickle.loads(pickle.dumps(m))
        assert m == m2
        assert len(m2) == 200

    def test_pickle_protocol_2(self):
        m = PersistentMap(x=10, y=20)
        m2 = pickle.loads(pickle.dumps(m, protocol=2))
        assert m == m2
