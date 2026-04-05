"""Nested path helpers for persistent collections.

Provides functional-style helpers for working with deeply nested
PersistentMap structures without manual intermediate variable tracking.
"""
from __future__ import annotations

from typing import Any, Callable, Sequence

from persistent_collections.persistent_map import PersistentMap


def assoc_in(
    collection: PersistentMap,
    keys: Sequence[Any],
    value: Any,
) -> PersistentMap:
    """Return *collection* with *value* set at the nested path *keys*.

    Intermediate maps are created automatically if they are absent.

    Example::

        m = PersistentMap()
        m2 = assoc_in(m, ['a', 'b', 'c'], 42)
        # m2['a']['b']['c'] == 42
    """
    if not keys:
        raise ValueError("keys must be non-empty")

    key = keys[0]
    if len(keys) == 1:
        return collection.set(key, value)

    # Recurse into the nested map (creating one if absent).
    inner = collection.get(key)
    if not isinstance(inner, PersistentMap):
        inner = PersistentMap()
    new_inner = assoc_in(inner, keys[1:], value)
    return collection.set(key, new_inner)


def update_in(
    collection: PersistentMap,
    keys: Sequence[Any],
    func: Callable[[Any], Any],
) -> PersistentMap:
    """Return *collection* with the nested value at *keys* replaced by ``func(old_value)``.

    If the path does not exist, ``func`` is called with ``None``.

    Example::

        m = PersistentMap().set('a', PersistentMap().set('count', 0))
        m2 = update_in(m, ['a', 'count'], lambda x: x + 1)
        # m2['a']['count'] == 1
    """
    if not keys:
        raise ValueError("keys must be non-empty")

    key = keys[0]
    if len(keys) == 1:
        old_value = collection.get(key, None)
        return collection.set(key, func(old_value))

    inner = collection.get(key)
    if not isinstance(inner, PersistentMap):
        inner = PersistentMap()
    new_inner = update_in(inner, keys[1:], func)
    return collection.set(key, new_inner)


def dissoc_in(
    collection: PersistentMap,
    keys: Sequence[Any],
) -> PersistentMap:
    """Return *collection* with the nested key at *keys* removed.

    Intermediate empty maps are pruned.  If the path does not exist the
    original collection is returned unchanged.

    Example::

        m = assoc_in(PersistentMap(), ['a', 'b'], 1)
        m2 = dissoc_in(m, ['a', 'b'])
        # 'b' is no longer present under 'a'
    """
    if not keys:
        raise ValueError("keys must be non-empty")

    key = keys[0]
    if len(keys) == 1:
        try:
            return collection.delete(key)
        except KeyError:
            return collection

    inner = collection.get(key)
    if not isinstance(inner, PersistentMap):
        # Path doesn't exist — nothing to do.
        return collection

    new_inner = dissoc_in(inner, keys[1:])
    return collection.set(key, new_inner)
