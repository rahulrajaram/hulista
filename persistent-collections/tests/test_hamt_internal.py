from __future__ import annotations

import pytest

from persistent_collections._hamt import _ArrayNode, _BitmapNode, _CollisionNode, _create_node


_UNSET = object()


class _FakeSubnode:
    def __init__(self, *, assoc_result=None, without_result=_UNSET, items_result=()) -> None:
        self._assoc_result = assoc_result
        self._without_result = without_result
        self._items_result = tuple(items_result)

    def find(self, shift: int, hash_val: int, key: object) -> object:
        return ("found", shift, hash_val, key)

    def assoc(self, shift: int, hash_val: int, key: object, value: object):
        if self._assoc_result is None:
            return self, False
        return self._assoc_result

    def without(self, shift: int, hash_val: int, key: object):
        if self._without_result is _UNSET:
            return self
        return self._without_result

    def items(self):
        yield from self._items_result


def test_array_node_find_and_assoc_variants() -> None:
    array = [None] * 32
    array[1] = ("a", 1)
    array[2] = _FakeSubnode(items_result=(("b", 2),))
    node = _ArrayNode(2, array)

    assert node.find(0, 1, "a") == 1
    assert node.find(0, 2, "b")[0] == "found"
    with pytest.raises(KeyError):
        node.find(0, 3, "missing")
    with pytest.raises(KeyError):
        node.find(0, 1, "wrong")

    same_node, added = node.assoc(0, 1, "a", 1)
    assert same_node is node
    assert added is False

    updated_node, added = node.assoc(0, 1, "a", 2)
    assert isinstance(updated_node, _ArrayNode)
    assert added is False

    colliding_node, added = node.assoc(0, 1, "other", 3)
    assert isinstance(colliding_node.array[1], (_BitmapNode, _CollisionNode))
    assert added is True

    changed_subnode, added = node.assoc(0, 2, "b", 4)
    assert isinstance(changed_subnode, _ArrayNode)
    assert added is False


def test_array_node_without_and_pack() -> None:
    subnode = _BitmapNode(1, ("b", 2))
    array = [None] * 32
    array[1] = ("a", 1)
    array[2] = subnode

    with pytest.raises(KeyError):
        _ArrayNode(1, [None] * 32).without(0, 1, "x")

    with pytest.raises(KeyError):
        _ArrayNode(1, [None, ("a", 1)] + [None] * 30).without(0, 1, "b")

    packed = _ArrayNode(1, [None, ("a", 1)] + [None] * 30)._pack(1)
    assert isinstance(packed, _BitmapNode)

    collapsed = _ArrayNode(16, array).without(0, 1, "a")
    assert isinstance(collapsed, _BitmapNode)


def test_bitmap_node_assoc_without_and_promote() -> None:
    node = _BitmapNode(1 << 1, ("a", 1))

    with pytest.raises(KeyError):
        node.find(0, 2, "missing")
    with pytest.raises(KeyError):
        node.find(0, 1, "wrong")

    same_node, added = node.assoc(0, 1, "a", 1)
    assert same_node is node
    assert added is False

    updated_node, added = node.assoc(0, 1, "a", 2)
    assert isinstance(updated_node, _BitmapNode)
    assert added is False

    colliding_node, added = node.assoc(0, 1, "b", 3)
    assert isinstance(colliding_node.array[1], (_BitmapNode, _CollisionNode))
    assert added is True

    dense_pairs = []
    bitmap = 0
    for i in range(16):
        bitmap |= 1 << i
        dense_pairs.extend((f"k{i}", i))
    dense = _BitmapNode(bitmap, tuple(dense_pairs))
    promoted, added = dense.assoc(0, 16, "new", 17)
    assert isinstance(promoted, _ArrayNode)
    assert added is True

    leaf_removed = node.without(0, 1, "a")
    assert leaf_removed is None

    subnode_bitmap = _BitmapNode(1 << 1, (None, _FakeSubnode(without_result=None)))
    assert subnode_bitmap.without(0, 1, "a") is None


def test_collision_node_assoc_without_and_create_node() -> None:
    collision = _create_node(32, 1, "a", 1, 1, "b", 2)
    assert isinstance(collision, _CollisionNode)
    assert collision.find(0, 1, "a") == 1

    updated, added = collision.assoc(0, 1, "a", 10)
    assert isinstance(updated, _CollisionNode)
    assert added is False

    expanded, added = collision.assoc(0, 1, "c", 3)
    assert isinstance(expanded, _CollisionNode)
    assert added is True

    different_hash, added = collision.assoc(0, 2, "z", 9)
    assert isinstance(different_hash, _BitmapNode)
    assert added is True

    single = collision.without(0, 1, "b")
    assert isinstance(single, _BitmapNode)
    with pytest.raises(KeyError):
        collision.without(0, 1, "missing")
