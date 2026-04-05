"""Comprehensive tests for PersistentVector."""
from __future__ import annotations

import collections.abc
import pytest

from persistent_collections import PersistentVector
from persistent_collections.persistent_vector import BRANCH_FACTOR


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_empty(self):
        v = PersistentVector()
        assert len(v) == 0

    def test_from_list(self):
        v = PersistentVector([1, 2, 3])
        assert len(v) == 3
        assert list(v) == [1, 2, 3]

    def test_from_tuple(self):
        v = PersistentVector((10, 20, 30))
        assert list(v) == [10, 20, 30]

    def test_from_generator(self):
        v = PersistentVector(x * x for x in range(5))
        assert list(v) == [0, 1, 4, 9, 16]

    def test_from_string_iterates_chars(self):
        v = PersistentVector("abc")
        assert list(v) == ['a', 'b', 'c']

    def test_none_iterable_is_empty(self):
        v = PersistentVector(None)
        assert len(v) == 0

    def test_heterogeneous_types(self):
        v = PersistentVector([1, "two", 3.0, None, True])
        assert v[0] == 1
        assert v[1] == "two"
        assert v[2] == 3.0
        assert v[3] is None
        assert v[4] is True


# ---------------------------------------------------------------------------
# __len__
# ---------------------------------------------------------------------------

class TestLen:
    def test_empty(self):
        assert len(PersistentVector()) == 0

    def test_single(self):
        assert len(PersistentVector([42])) == 1

    def test_many(self):
        v = PersistentVector(range(100))
        assert len(v) == 100

    def test_len_after_sequential_appends(self):
        v = PersistentVector()
        for i in range(50):
            v = v.append(i)
            assert len(v) == i + 1


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------

class TestAppend:
    def test_append_to_empty(self):
        v = PersistentVector().append(99)
        assert len(v) == 1
        assert v[0] == 99

    def test_append_returns_new_vector(self):
        v1 = PersistentVector([1, 2])
        v2 = v1.append(3)
        assert v2 is not v1
        assert list(v1) == [1, 2]
        assert list(v2) == [1, 2, 3]

    def test_original_unchanged_after_append(self):
        v1 = PersistentVector(range(10))
        _v2 = v1.append(99)
        assert list(v1) == list(range(10))

    def test_chain_of_appends(self):
        v = PersistentVector()
        for i in range(200):
            v = v.append(i)
        assert list(v) == list(range(200))

    def test_append_across_tail_boundary(self):
        # Fill exactly one tail (32 elements), then push one more
        v = PersistentVector(range(BRANCH_FACTOR))
        v2 = v.append(BRANCH_FACTOR)
        assert len(v2) == BRANCH_FACTOR + 1
        assert v2[BRANCH_FACTOR] == BRANCH_FACTOR

    def test_append_triggers_trie_growth(self):
        # After 32*32 = 1024 elements the trie must grow a level
        count = BRANCH_FACTOR * BRANCH_FACTOR + 1
        v = PersistentVector(range(count))
        assert len(v) == count
        assert list(v) == list(range(count))

    def test_structural_sharing(self):
        base = PersistentVector(range(100))
        v1 = base.append("a")
        v2 = base.append("b")
        # They share the same root (tail is not full yet)
        assert v1._root is v2._root
        assert v1._root is base._root
        assert list(v1)[:100] == list(range(100))
        assert list(v2)[:100] == list(range(100))


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------

class TestSet:
    def test_set_returns_new_vector(self):
        v1 = PersistentVector([1, 2, 3])
        v2 = v1.set(1, 99)
        assert v2 is not v1
        assert list(v1) == [1, 2, 3]
        assert list(v2) == [1, 99, 3]

    def test_set_first_element(self):
        v = PersistentVector(range(10)).set(0, -1)
        assert v[0] == -1
        assert list(v[1:]) == list(range(1, 10))

    def test_set_last_element(self):
        v = PersistentVector(range(10)).set(9, 999)
        assert v[9] == 999

    def test_set_negative_index(self):
        v = PersistentVector([10, 20, 30])
        v2 = v.set(-1, 99)
        assert list(v2) == [10, 20, 99]

    def test_set_negative_index_first(self):
        v = PersistentVector([10, 20, 30])
        v2 = v.set(-3, 0)
        assert list(v2) == [0, 20, 30]

    def test_set_out_of_range_raises(self):
        v = PersistentVector([1, 2, 3])
        with pytest.raises(IndexError):
            v.set(3, 99)

    def test_set_negative_out_of_range_raises(self):
        v = PersistentVector([1, 2, 3])
        with pytest.raises(IndexError):
            v.set(-4, 99)

    def test_set_in_trie_portion(self):
        # Elements before the tail are in the trie
        v = PersistentVector(range(100))
        v2 = v.set(0, -999)
        assert v2[0] == -999
        assert v[0] == 0  # original unchanged

    def test_set_in_tail_portion(self):
        v = PersistentVector(range(100))
        # Element 99 is in the tail (offset 96, tail index 3)
        v2 = v.set(99, 777)
        assert v2[99] == 777
        assert v[99] == 99

    def test_set_chained(self):
        v = PersistentVector(range(5))
        v2 = v.set(0, 10).set(2, 20).set(4, 40)
        assert list(v2) == [10, 1, 20, 3, 40]


# ---------------------------------------------------------------------------
# __getitem__
# ---------------------------------------------------------------------------

class TestGetItem:
    def test_positive_index(self):
        v = PersistentVector([10, 20, 30])
        assert v[0] == 10
        assert v[1] == 20
        assert v[2] == 30

    def test_negative_index(self):
        v = PersistentVector([10, 20, 30])
        assert v[-1] == 30
        assert v[-2] == 20
        assert v[-3] == 10

    def test_index_out_of_range_raises(self):
        v = PersistentVector([1, 2, 3])
        with pytest.raises(IndexError):
            _ = v[3]

    def test_negative_out_of_range_raises(self):
        v = PersistentVector([1, 2, 3])
        with pytest.raises(IndexError):
            _ = v[-4]

    def test_empty_raises(self):
        v = PersistentVector()
        with pytest.raises(IndexError):
            _ = v[0]

    def test_slice_basic(self):
        v = PersistentVector(range(10))
        s = v[2:5]
        assert isinstance(s, PersistentVector)
        assert list(s) == [2, 3, 4]

    def test_slice_full(self):
        v = PersistentVector(range(5))
        assert list(v[:]) == list(range(5))

    def test_slice_step(self):
        v = PersistentVector(range(10))
        assert list(v[::2]) == [0, 2, 4, 6, 8]

    def test_slice_negative(self):
        v = PersistentVector(range(5))
        assert list(v[-3:]) == [2, 3, 4]

    def test_access_across_tail_boundary(self):
        v = PersistentVector(range(BRANCH_FACTOR + 5))
        # Elements in the trie
        assert v[0] == 0
        assert v[BRANCH_FACTOR - 1] == BRANCH_FACTOR - 1
        # Elements in the tail
        assert v[BRANCH_FACTOR] == BRANCH_FACTOR
        assert v[BRANCH_FACTOR + 4] == BRANCH_FACTOR + 4


# ---------------------------------------------------------------------------
# __iter__
# ---------------------------------------------------------------------------

class TestIter:
    def test_empty(self):
        assert list(PersistentVector()) == []

    def test_produces_correct_sequence(self):
        data = list(range(50))
        v = PersistentVector(data)
        assert list(v) == data

    def test_iter_large(self):
        data = list(range(1000))
        v = PersistentVector(data)
        assert list(v) == data

    def test_iter_multiple_times(self):
        v = PersistentVector([1, 2, 3])
        assert list(v) == list(v)


# ---------------------------------------------------------------------------
# __hash__
# ---------------------------------------------------------------------------

class TestHash:
    def test_hashable(self):
        v = PersistentVector([1, 2, 3])
        h = hash(v)
        assert isinstance(h, int)

    def test_can_be_dict_key(self):
        v = PersistentVector([1, 2, 3])
        d = {v: "found"}
        assert d[v] == "found"

    def test_equal_vectors_same_hash(self):
        v1 = PersistentVector([1, 2, 3])
        v2 = PersistentVector([1, 2, 3])
        assert hash(v1) == hash(v2)

    def test_hash_matches_tuple(self):
        v = PersistentVector([1, 2, 3])
        assert hash(v) == hash((1, 2, 3))

    def test_hash_cached(self):
        v = PersistentVector([1, 2, 3])
        h1 = hash(v)
        h2 = hash(v)
        assert h1 == h2

    def test_empty_hash(self):
        v = PersistentVector()
        assert hash(v) == hash(())

    def test_can_be_set_member(self):
        v1 = PersistentVector([1, 2])
        v2 = PersistentVector([3, 4])
        s = {v1, v2}
        assert v1 in s
        assert v2 in s


# ---------------------------------------------------------------------------
# __eq__
# ---------------------------------------------------------------------------

class TestEquality:
    def test_equal_vectors(self):
        v1 = PersistentVector([1, 2, 3])
        v2 = PersistentVector([1, 2, 3])
        assert v1 == v2

    def test_different_vectors(self):
        v1 = PersistentVector([1, 2, 3])
        v2 = PersistentVector([1, 2, 4])
        assert v1 != v2

    def test_different_lengths(self):
        v1 = PersistentVector([1, 2])
        v2 = PersistentVector([1, 2, 3])
        assert v1 != v2

    def test_equal_to_list(self):
        v = PersistentVector([1, 2, 3])
        assert v == [1, 2, 3]

    def test_equal_to_tuple(self):
        v = PersistentVector([1, 2, 3])
        assert v == (1, 2, 3)

    def test_not_equal_to_different_list(self):
        v = PersistentVector([1, 2, 3])
        assert v != [1, 2]

    def test_not_equal_to_string(self):
        v = PersistentVector(['a', 'b', 'c'])
        assert v != "abc"

    def test_empty_vectors_equal(self):
        assert PersistentVector() == PersistentVector()

    def test_empty_equal_empty_list(self):
        assert PersistentVector() == []

    def test_same_object_equal(self):
        v = PersistentVector([1, 2, 3])
        assert v == v

    def test_identity_shortcut(self):
        base = PersistentVector(range(50))
        v = base.append(99)
        # These share _root; equality still works correctly
        assert v != base

    def test_equal_to_list_with_same_object_nan(self):
        nan = float("nan")
        v = PersistentVector([nan])
        assert v == [nan]

    def test_equal_to_tuple_with_same_object_nan(self):
        nan = float("nan")
        v = PersistentVector([nan])
        assert v == (nan,)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_setattr_raises(self):
        v = PersistentVector([1, 2, 3])
        with pytest.raises(AttributeError):
            v._count = 99  # type: ignore[misc]

    def test_delattr_raises(self):
        v = PersistentVector([1, 2, 3])
        with pytest.raises(AttributeError):
            del v._count  # type: ignore[misc]

    def test_arbitrary_attr_raises(self):
        v = PersistentVector()
        with pytest.raises(AttributeError):
            v.new_attr = "oops"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Concatenation (__add__)
# ---------------------------------------------------------------------------

class TestConcat:
    def test_add_list(self):
        v = PersistentVector([1, 2]) + [3, 4]
        assert list(v) == [1, 2, 3, 4]

    def test_add_tuple(self):
        v = PersistentVector([1, 2]) + (3, 4)
        assert list(v) == [1, 2, 3, 4]

    def test_add_persistent_vector(self):
        v1 = PersistentVector([1, 2])
        v2 = PersistentVector([3, 4])
        v3 = v1 + v2
        assert list(v3) == [1, 2, 3, 4]

    def test_add_empty(self):
        v = PersistentVector([1, 2, 3]) + []
        assert list(v) == [1, 2, 3]

    def test_add_to_empty(self):
        v = PersistentVector() + [1, 2, 3]
        assert list(v) == [1, 2, 3]

    def test_add_returns_persistent_vector(self):
        result = PersistentVector([1]) + [2]
        assert isinstance(result, PersistentVector)

    def test_add_unsupported_type_returns_not_implemented(self):
        v = PersistentVector([1, 2])
        result = v.__add__("string")
        assert result is NotImplemented


# ---------------------------------------------------------------------------
# Sequence ABC
# ---------------------------------------------------------------------------

class TestSequenceABC:
    def test_is_sequence(self):
        v = PersistentVector([1, 2, 3])
        assert isinstance(v, collections.abc.Sequence)

    def test_count_method(self):
        v = PersistentVector([1, 2, 2, 3, 2])
        assert v.count(2) == 3

    def test_index_method(self):
        v = PersistentVector([10, 20, 30])
        assert v.index(20) == 1

    def test_reversed(self):
        v = PersistentVector([1, 2, 3])
        assert list(reversed(v)) == [3, 2, 1]

    def test_contains(self):
        v = PersistentVector([1, 2, 3])
        assert 2 in v
        assert 99 not in v


# ---------------------------------------------------------------------------
# Large vector stress tests
# ---------------------------------------------------------------------------

class TestLargeVector:
    N = 10_000

    def test_10000_appends(self):
        v = PersistentVector(range(self.N))
        assert len(v) == self.N

    def test_all_elements_accessible(self):
        v = PersistentVector(range(self.N))
        for i in range(self.N):
            assert v[i] == i

    def test_set_every_element(self):
        v = PersistentVector(range(self.N))
        for i in range(0, self.N, 1000):
            v2 = v.set(i, -i)
            assert v2[i] == -i
            assert v[i] == i  # original unchanged

    def test_iter_10000(self):
        v = PersistentVector(range(self.N))
        assert list(v) == list(range(self.N))

    def test_negative_index_large(self):
        v = PersistentVector(range(self.N))
        assert v[-1] == self.N - 1
        assert v[-self.N] == 0

    def test_hash_large(self):
        v = PersistentVector(range(self.N))
        h = hash(v)
        assert isinstance(h, int)
        # Stable
        assert hash(v) == h


# ---------------------------------------------------------------------------
# Structural sharing details
# ---------------------------------------------------------------------------

class TestStructuralSharing:
    def test_two_vectors_share_root(self):
        """Appending to the same base produces vectors sharing the trie root.

        Use a base whose tail is not yet full so both appends stay in the tail
        and no push-tail into the trie occurs — root identity is preserved.
        """
        # 100 elements: tail_offset = 96, tail has 4 elements (not full at 32)
        base = PersistentVector(range(100))
        v1 = base.append("x")
        v2 = base.append("y")
        # Both appends only extend the tail, so root is untouched
        assert v1._root is base._root
        assert v2._root is base._root

    def test_independent_tails(self):
        base = PersistentVector(range(64))
        v1 = base.append("x")
        v2 = base.append("y")
        assert v1._tail != v2._tail
        assert v1[-1] == "x"
        assert v2[-1] == "y"

    def test_old_version_intact_after_set(self):
        v1 = PersistentVector(range(1000))
        v2 = v1.set(500, -1)
        assert v1[500] == 500
        assert v2[500] == -1
        # All other elements identical
        for i in range(1000):
            if i != 500:
                assert v1[i] == v2[i]


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------

class TestRepr:
    def test_empty_repr(self):
        assert repr(PersistentVector()) == "PersistentVector([])"

    def test_short_repr(self):
        v = PersistentVector([1, 2, 3])
        assert repr(v) == "PersistentVector([1, 2, 3])"

    def test_long_repr_truncated(self):
        v = PersistentVector(range(20))
        r = repr(v)
        # repr shows first 10 items then "..." before the closing bracket
        assert r.endswith("...])")
        assert "PersistentVector([" in r
        assert ", ..." in r
