"""Tests for nested path helpers: assoc_in, update_in, dissoc_in."""
from __future__ import annotations

import pytest

from persistent_collections import PersistentMap, assoc_in, update_in, dissoc_in


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def nested_map(**kwargs) -> PersistentMap:
    return PersistentMap.from_dict(kwargs)


# ---------------------------------------------------------------------------
# assoc_in
# ---------------------------------------------------------------------------

class TestAssocIn:
    def test_single_key(self):
        m = PersistentMap()
        m2 = assoc_in(m, ['a'], 42)
        assert m2['a'] == 42

    def test_two_level_key(self):
        m = PersistentMap()
        m2 = assoc_in(m, ['a', 'b'], 99)
        assert m2['a']['b'] == 99

    def test_three_level_key(self):
        m = PersistentMap()
        m2 = assoc_in(m, ['a', 'b', 'c'], 'deep')
        assert m2['a']['b']['c'] == 'deep'

    def test_creates_intermediate_maps(self):
        m = PersistentMap()
        m2 = assoc_in(m, ['x', 'y'], 1)
        assert isinstance(m2['x'], PersistentMap)

    def test_preserves_sibling_keys(self):
        m = PersistentMap.from_dict({'a': PersistentMap.from_dict({'x': 1}), 'b': 2})
        m2 = assoc_in(m, ['a', 'y'], 99)
        assert m2['a']['x'] == 1
        assert m2['a']['y'] == 99
        assert m2['b'] == 2

    def test_overwrite_existing_value(self):
        m = assoc_in(PersistentMap(), ['a', 'b'], 'old')
        m2 = assoc_in(m, ['a', 'b'], 'new')
        assert m2['a']['b'] == 'new'

    def test_does_not_mutate_original(self):
        m = assoc_in(PersistentMap(), ['a', 'b'], 1)
        assoc_in(m, ['a', 'b'], 99)
        assert m['a']['b'] == 1

    def test_empty_keys_raises(self):
        with pytest.raises(ValueError):
            assoc_in(PersistentMap(), [], 1)

    def test_returns_new_map(self):
        m = PersistentMap()
        m2 = assoc_in(m, ['k'], 'v')
        assert m is not m2

    def test_non_string_keys(self):
        m = PersistentMap()
        m2 = assoc_in(m, [1, 2, 3], 'value')
        assert m2[1][2][3] == 'value'

    def test_overwrites_non_map_with_map(self):
        """If an intermediate key holds a non-map value it is replaced."""
        m = PersistentMap.from_dict({'a': 'not a map'})
        m2 = assoc_in(m, ['a', 'b'], 1)
        assert isinstance(m2['a'], PersistentMap)
        assert m2['a']['b'] == 1


# ---------------------------------------------------------------------------
# update_in
# ---------------------------------------------------------------------------

class TestUpdateIn:
    def test_update_existing_value(self):
        m = assoc_in(PersistentMap(), ['count'], 5)
        m2 = update_in(m, ['count'], lambda x: x + 1)
        assert m2['count'] == 6

    def test_update_nested(self):
        m = assoc_in(PersistentMap(), ['a', 'b'], 10)
        m2 = update_in(m, ['a', 'b'], lambda x: x * 2)
        assert m2['a']['b'] == 20

    def test_update_absent_key_passes_none(self):
        m = PersistentMap()
        m2 = update_in(m, ['missing'], lambda x: (x or 0) + 1)
        assert m2['missing'] == 1

    def test_update_creates_intermediate_maps(self):
        m = PersistentMap()
        m2 = update_in(m, ['a', 'b'], lambda x: (x or 0) + 5)
        assert m2['a']['b'] == 5

    def test_update_does_not_mutate_original(self):
        m = assoc_in(PersistentMap(), ['a'], 1)
        update_in(m, ['a'], lambda x: x + 99)
        assert m['a'] == 1

    def test_empty_keys_raises(self):
        with pytest.raises(ValueError):
            update_in(PersistentMap(), [], lambda x: x)

    def test_update_with_str_concat(self):
        m = assoc_in(PersistentMap(), ['msg'], 'hello')
        m2 = update_in(m, ['msg'], lambda x: x + ' world')
        assert m2['msg'] == 'hello world'

    def test_update_preserves_siblings(self):
        m = PersistentMap.from_dict({'a': PersistentMap.from_dict({'x': 1, 'y': 2})})
        m2 = update_in(m, ['a', 'x'], lambda v: v + 10)
        assert m2['a']['x'] == 11
        assert m2['a']['y'] == 2


# ---------------------------------------------------------------------------
# dissoc_in
# ---------------------------------------------------------------------------

class TestDissocIn:
    def test_remove_single_key(self):
        m = PersistentMap.from_dict({'a': 1, 'b': 2})
        m2 = dissoc_in(m, ['a'])
        assert 'a' not in m2
        assert m2['b'] == 2

    def test_remove_nested_key(self):
        m = assoc_in(PersistentMap(), ['a', 'b'], 1)
        m2 = dissoc_in(m, ['a', 'b'])
        assert 'b' not in m2['a']

    def test_remove_absent_key_is_noop(self):
        m = PersistentMap.from_dict({'a': 1})
        m2 = dissoc_in(m, ['missing'])
        assert m2 == m

    def test_remove_absent_nested_key_is_noop(self):
        m = assoc_in(PersistentMap(), ['a', 'b'], 1)
        m2 = dissoc_in(m, ['a', 'c'])
        assert m2 == m

    def test_remove_path_on_non_map_intermediate_is_noop(self):
        m = PersistentMap.from_dict({'a': 'not a map'})
        m2 = dissoc_in(m, ['a', 'b'])
        assert m2 == m

    def test_does_not_mutate_original(self):
        m = assoc_in(PersistentMap(), ['a', 'b'], 99)
        dissoc_in(m, ['a', 'b'])
        assert m['a']['b'] == 99

    def test_empty_keys_raises(self):
        with pytest.raises(ValueError):
            dissoc_in(PersistentMap(), [])

    def test_returns_new_map(self):
        m = PersistentMap.from_dict({'x': 1})
        m2 = dissoc_in(m, ['x'])
        assert m is not m2

    def test_remove_deeply_nested(self):
        m = assoc_in(PersistentMap(), ['a', 'b', 'c', 'd'], 'leaf')
        m2 = dissoc_in(m, ['a', 'b', 'c', 'd'])
        assert 'd' not in m2['a']['b']['c']

    def test_sibling_keys_preserved(self):
        m = assoc_in(PersistentMap(), ['a', 'x'], 1)
        m = assoc_in(m, ['a', 'y'], 2)
        m2 = dissoc_in(m, ['a', 'x'])
        assert 'x' not in m2['a']
        assert m2['a']['y'] == 2


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

class TestComposition:
    def test_assoc_then_update(self):
        m = assoc_in(PersistentMap(), ['counters', 'clicks'], 0)
        m2 = update_in(m, ['counters', 'clicks'], lambda x: x + 5)
        assert m2['counters']['clicks'] == 5

    def test_assoc_then_dissoc_round_trip(self):
        m = PersistentMap()
        m2 = assoc_in(m, ['a', 'b'], 'hello')
        m3 = dissoc_in(m2, ['a', 'b'])
        assert 'b' not in m3['a']

    def test_multiple_assoc_in_independence(self):
        base = PersistentMap()
        m1 = assoc_in(base, ['a', 'b'], 1)
        m2 = assoc_in(base, ['a', 'b'], 2)
        assert m1['a']['b'] == 1
        assert m2['a']['b'] == 2
