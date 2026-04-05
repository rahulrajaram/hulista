"""Tests for TransientVector."""
from __future__ import annotations

import pickle

import pytest

from persistent_collections import PersistentVector, TransientVector


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_empty_transient(self):
        t = TransientVector()
        assert len(t) == 0

    def test_from_persistent_vector(self):
        pv = PersistentVector([1, 2, 3])
        t = TransientVector(pv)
        assert len(t) == 3
        assert t[0] == 1
        assert t[1] == 2
        assert t[2] == 3

    def test_from_none_starts_empty(self):
        t = TransientVector(None)
        assert len(t) == 0

    def test_persistent_vector_transient_method(self):
        pv = PersistentVector([10, 20])
        t = pv.transient()
        assert isinstance(t, TransientVector)
        assert t[0] == 10


# ---------------------------------------------------------------------------
# append / __setitem__ / __getitem__
# ---------------------------------------------------------------------------

class TestMutation:
    def test_append(self):
        t = TransientVector()
        t.append(1)
        t.append(2)
        t.append(3)
        assert len(t) == 3
        assert t[0] == 1
        assert t[2] == 3

    def test_setitem(self):
        t = TransientVector()
        t.append(10)
        t.append(20)
        t[0] = 99
        assert t[0] == 99
        assert t[1] == 20

    def test_setitem_negative_index(self):
        t = TransientVector()
        t.append('a')
        t.append('b')
        t[-1] = 'z'
        assert t[1] == 'z'

    def test_getitem_out_of_range(self):
        t = TransientVector()
        t.append(1)
        with pytest.raises(IndexError):
            _ = t[10]

    def test_append_many(self):
        t = TransientVector()
        for i in range(100):
            t.append(i)
        assert len(t) == 100
        for i in range(100):
            assert t[i] == i


# ---------------------------------------------------------------------------
# persistent() — freeze
# ---------------------------------------------------------------------------

class TestPersistent:
    def test_persistent_returns_persistent_vector(self):
        t = TransientVector()
        t.append(1)
        pv = t.persistent()
        assert isinstance(pv, PersistentVector)

    def test_persistent_has_correct_values(self):
        t = TransientVector()
        for i in range(10):
            t.append(i)
        pv = t.persistent()
        assert list(pv) == list(range(10))

    def test_persistent_vector_is_immutable(self):
        t = TransientVector()
        t.append(1)
        pv = t.persistent()
        pv2 = pv.append(2)
        assert len(pv) == 1
        assert len(pv2) == 2

    def test_persistent_from_empty(self):
        t = TransientVector()
        pv = t.persistent()
        assert len(pv) == 0


# ---------------------------------------------------------------------------
# Frozen transient raises on mutation
# ---------------------------------------------------------------------------

class TestFrozen:
    def test_append_after_frozen_raises(self):
        t = TransientVector()
        t.persistent()
        with pytest.raises(RuntimeError):
            t.append(1)

    def test_setitem_after_frozen_raises(self):
        t = TransientVector()
        t.append(10)
        t.persistent()
        with pytest.raises(RuntimeError):
            t[0] = 99

    def test_error_message_mentions_frozen(self):
        t = TransientVector()
        t.persistent()
        with pytest.raises(RuntimeError, match="frozen"):
            t.append(1)

    def test_read_still_works_after_frozen(self):
        t = TransientVector()
        t.append(42)
        t.persistent()
        assert t[0] == 42


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_basic(self):
        t = TransientVector()
        with t as tv:
            tv.append(1)
            tv.append(2)
        pv = t.persistent()
        assert list(pv) == [1, 2]

    def test_context_manager_returns_self(self):
        t = TransientVector()
        with t as tv:
            assert tv is t

    def test_context_manager_freezes_on_exit(self):
        t = TransientVector()
        with t:
            t.append(1)
        with pytest.raises(RuntimeError):
            t.append(2)

    def test_context_manager_exception_propagates(self):
        t = TransientVector()
        with pytest.raises(ValueError):
            with t as tv:
                tv.append(1)
                raise ValueError("oops")
        assert t[0] == 1

    def test_context_manager_many_items(self):
        t = TransientVector()
        with t as tv:
            for i in range(50):
                tv.append(i)
        pv = t.persistent()
        assert len(pv) == 50
        assert pv[7] == 7


# ---------------------------------------------------------------------------
# Building from existing PersistentVector
# ---------------------------------------------------------------------------

class TestFromPersistentVector:
    def test_inherits_values(self):
        pv = PersistentVector([10, 20, 30])
        t = TransientVector(pv)
        assert t[0] == 10
        assert t[2] == 30

    def test_can_append_to_existing(self):
        pv = PersistentVector([1, 2])
        t = TransientVector(pv)
        t.append(3)
        result = t.persistent()
        assert list(result) == [1, 2, 3]

    def test_can_modify_existing(self):
        pv = PersistentVector([1, 2, 3])
        t = TransientVector(pv)
        t[1] = 99
        result = t.persistent()
        assert list(result) == [1, 99, 3]

    def test_original_vector_unchanged(self):
        pv = PersistentVector([1, 2, 3])
        t = pv.transient()
        t.append(4)
        t[0] = 99
        assert list(pv) == [1, 2, 3]


# ---------------------------------------------------------------------------
# PersistentVector serialisation
# ---------------------------------------------------------------------------

class TestVectorSerialisation:
    def test_to_list(self):
        pv = PersistentVector([1, 2, 3])
        assert pv.to_list() == [1, 2, 3]

    def test_from_list(self):
        pv = PersistentVector.from_list([4, 5, 6])
        assert list(pv) == [4, 5, 6]

    def test_to_list_empty(self):
        assert PersistentVector().to_list() == []

    def test_from_list_empty(self):
        pv = PersistentVector.from_list([])
        assert len(pv) == 0

    def test_pickle_empty(self):
        pv = PersistentVector()
        pv2 = pickle.loads(pickle.dumps(pv))
        assert list(pv2) == []

    def test_pickle_with_values(self):
        pv = PersistentVector([1, 2, 3, 4, 5])
        pv2 = pickle.loads(pickle.dumps(pv))
        assert list(pv2) == [1, 2, 3, 4, 5]

    def test_pickle_large_vector(self):
        pv = PersistentVector(range(500))
        pv2 = pickle.loads(pickle.dumps(pv))
        assert list(pv2) == list(range(500))

    def test_pickle_protocol_2(self):
        pv = PersistentVector([10, 20, 30])
        pv2 = pickle.loads(pickle.dumps(pv, protocol=2))
        assert list(pv2) == [10, 20, 30]

    def test_round_trip_to_from_list(self):
        original = list(range(100))
        pv = PersistentVector.from_list(original)
        assert pv.to_list() == original
