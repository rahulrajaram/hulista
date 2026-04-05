"""Tests for PersistentSet."""
from __future__ import annotations

import pytest

from persistent_collections import PersistentSet


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_empty_set(self):
        s = PersistentSet()
        assert len(s) == 0

    def test_from_iterable(self):
        s = PersistentSet([1, 2, 3])
        assert len(s) == 3

    def test_from_iterable_deduplicates(self):
        s = PersistentSet([1, 1, 2, 2, 3])
        assert len(s) == 3

    def test_from_empty_iterable(self):
        s = PersistentSet([])
        assert len(s) == 0

    def test_from_strings(self):
        s = PersistentSet("abc")
        assert len(s) == 3
        assert 'a' in s
        assert 'b' in s
        assert 'c' in s


# ---------------------------------------------------------------------------
# add / discard / __contains__
# ---------------------------------------------------------------------------

class TestMutation:
    def test_add_returns_new_set(self):
        s1 = PersistentSet()
        s2 = s1.add(1)
        assert s1 is not s2
        assert 1 not in s1
        assert 1 in s2

    def test_add_increases_len(self):
        s = PersistentSet()
        s = s.add('x')
        assert len(s) == 1

    def test_add_same_element_returns_self(self):
        sentinel = object()
        s1 = PersistentSet().add(sentinel)
        s2 = s1.add(sentinel)
        assert s2 is s1

    def test_add_duplicate_does_not_increase_len(self):
        s = PersistentSet([1, 2, 3])
        s2 = s.add(2)
        assert len(s2) == 3

    def test_discard_removes_element(self):
        s = PersistentSet([1, 2, 3])
        s2 = s.discard(2)
        assert 2 not in s2
        assert len(s2) == 2

    def test_discard_absent_element_returns_equal_set(self):
        s = PersistentSet([1, 2, 3])
        s2 = s.discard(99)
        assert s2 == s

    def test_discard_original_unchanged(self):
        s = PersistentSet([1, 2, 3])
        _ = s.discard(1)
        assert 1 in s

    def test_contains_present(self):
        s = PersistentSet(['a', 'b'])
        assert 'a' in s
        assert 'b' in s

    def test_contains_absent(self):
        s = PersistentSet(['a'])
        assert 'z' not in s

    def test_contains_unhashable_returns_false(self):
        s = PersistentSet([1, 2])
        assert [] not in s


# ---------------------------------------------------------------------------
# __iter__
# ---------------------------------------------------------------------------

class TestIteration:
    def test_iter_empty(self):
        assert list(PersistentSet()) == []

    def test_iter_yields_all_elements(self):
        s = PersistentSet([1, 2, 3])
        assert set(s) == {1, 2, 3}

    def test_iter_no_duplicates(self):
        s = PersistentSet([1, 1, 2, 2])
        assert len(list(s)) == 2

    def test_iter_large(self):
        s = PersistentSet(range(200))
        assert set(s) == set(range(200))


# ---------------------------------------------------------------------------
# Set algebra
# ---------------------------------------------------------------------------

class TestSetAlgebra:
    def test_union(self):
        a = PersistentSet([1, 2, 3])
        b = PersistentSet([3, 4, 5])
        u = a | b
        assert set(u) == {1, 2, 3, 4, 5}

    def test_union_returns_persistent_set(self):
        a = PersistentSet([1])
        b = PersistentSet([2])
        assert isinstance(a | b, PersistentSet)

    def test_intersection(self):
        a = PersistentSet([1, 2, 3])
        b = PersistentSet([2, 3, 4])
        i = a & b
        assert set(i) == {2, 3}

    def test_intersection_disjoint(self):
        a = PersistentSet([1, 2])
        b = PersistentSet([3, 4])
        assert len(a & b) == 0

    def test_difference(self):
        a = PersistentSet([1, 2, 3, 4])
        b = PersistentSet([2, 4])
        d = a - b
        assert set(d) == {1, 3}

    def test_difference_removes_all_from_other(self):
        a = PersistentSet([1, 2])
        b = PersistentSet([1, 2, 3])
        d = a - b
        assert len(d) == 0

    def test_symmetric_difference(self):
        a = PersistentSet([1, 2, 3])
        b = PersistentSet([2, 3, 4])
        xor = a ^ b
        assert set(xor) == {1, 4}

    def test_symmetric_difference_disjoint(self):
        a = PersistentSet([1, 2])
        b = PersistentSet([3, 4])
        assert set(a ^ b) == {1, 2, 3, 4}

    def test_union_with_frozenset(self):
        a = PersistentSet([1, 2])
        u = a | frozenset([3, 4])
        assert set(u) == {1, 2, 3, 4}

    def test_intersection_with_frozenset(self):
        a = PersistentSet([1, 2, 3])
        i = a & frozenset([2, 3, 4])
        assert set(i) == {2, 3}


# ---------------------------------------------------------------------------
# issubset / issuperset
# ---------------------------------------------------------------------------

class TestSubsetSuperset:
    def test_issubset_true(self):
        a = PersistentSet([1, 2])
        b = PersistentSet([1, 2, 3])
        assert a.issubset(b)

    def test_issubset_equal(self):
        a = PersistentSet([1, 2])
        assert a.issubset(PersistentSet([1, 2]))

    def test_issubset_false(self):
        a = PersistentSet([1, 2, 3])
        b = PersistentSet([1, 2])
        assert not a.issubset(b)

    def test_issuperset_true(self):
        a = PersistentSet([1, 2, 3])
        b = PersistentSet([1, 2])
        assert a.issuperset(b)

    def test_issuperset_false(self):
        a = PersistentSet([1, 2])
        b = PersistentSet([1, 2, 3])
        assert not a.issuperset(b)

    def test_issubset_with_plain_set(self):
        a = PersistentSet([1, 2])
        assert a.issubset({1, 2, 3})

    def test_issuperset_with_plain_set(self):
        a = PersistentSet([1, 2, 3])
        assert a.issuperset({1, 2})


# ---------------------------------------------------------------------------
# Hashing and equality
# ---------------------------------------------------------------------------

class TestHashEquality:
    def test_hashable(self):
        s = PersistentSet([1, 2, 3])
        assert isinstance(hash(s), int)

    def test_empty_hashable(self):
        assert isinstance(hash(PersistentSet()), int)

    def test_equal_sets_same_hash(self):
        s1 = PersistentSet([1, 2, 3])
        s2 = PersistentSet([3, 1, 2])
        assert s1 == s2
        assert hash(s1) == hash(s2)

    def test_usable_as_dict_key(self):
        s = PersistentSet([1, 2])
        d = {s: 'value'}
        assert d[s] == 'value'

    def test_equal_to_frozenset(self):
        s = PersistentSet([1, 2, 3])
        assert s == frozenset([1, 2, 3])

    def test_not_equal_different_elements(self):
        s1 = PersistentSet([1, 2])
        s2 = PersistentSet([1, 3])
        assert s1 != s2

    def test_hash_stable(self):
        s = PersistentSet([1, 2, 3])
        assert hash(s) == hash(s)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_setattr_raises(self):
        s = PersistentSet()
        with pytest.raises(AttributeError, match="immutable"):
            s.foo = 'bar'  # type: ignore[attr-defined]

    def test_delattr_raises(self):
        s = PersistentSet()
        with pytest.raises(AttributeError, match="immutable"):
            del s._root  # type: ignore[attr-defined]

    def test_add_does_not_mutate_original(self):
        s1 = PersistentSet([1, 2])
        _ = s1.add(3)
        assert 3 not in s1

    def test_discard_does_not_mutate_original(self):
        s1 = PersistentSet([1, 2])
        _ = s1.discard(1)
        assert 1 in s1


# ---------------------------------------------------------------------------
# Large set stress
# ---------------------------------------------------------------------------

class TestLargeSet:
    def test_insert_1000_elements(self):
        s = PersistentSet()
        for i in range(1000):
            s = s.add(i)
        assert len(s) == 1000
        for i in range(1000):
            assert i in s

    def test_discard_500_elements(self):
        s = PersistentSet(range(1000))
        for i in range(0, 1000, 2):
            s = s.discard(i)
        assert len(s) == 500
        for i in range(1, 1000, 2):
            assert i in s


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr_empty(self):
        assert repr(PersistentSet()) == 'PersistentSet({})'

    def test_repr_contains_elements(self):
        s = PersistentSet([42])
        assert '42' in repr(s)
        assert 'PersistentSet' in repr(s)
