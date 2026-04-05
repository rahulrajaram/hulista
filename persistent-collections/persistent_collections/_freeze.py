from __future__ import annotations

from typing import Any

from persistent_collections.persistent_map import PersistentMap
from persistent_collections.persistent_vector import PersistentVector


def freeze(obj: Any) -> Any:
    """Recursively convert plain Python collections to persistent equivalents.

    - ``dict`` -> ``PersistentMap`` (keys preserved, values recursively frozen)
    - ``list`` / ``tuple`` -> ``PersistentVector`` (elements recursively frozen)
    - All other values pass through unchanged (strings, ints, dataclasses, etc.)

    Already-persistent structures (PersistentMap, PersistentVector) pass through
    without re-conversion.

    Usage::

        data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
        frozen = freeze(data)
        # PersistentMap({"users": PersistentVector([PersistentMap({"name": "Alice"}), ...])})
    """
    if isinstance(obj, PersistentMap):
        return obj  # already frozen
    if isinstance(obj, PersistentVector):
        return obj  # already frozen
    if isinstance(obj, dict):
        m: PersistentMap[Any, Any] = PersistentMap()
        for k, v in obj.items():
            m = m.set(k, freeze(v))
        return m
    if isinstance(obj, (list, tuple)):
        vec: PersistentVector[Any] = PersistentVector()
        for item in obj:
            vec = vec.append(freeze(item))
        return vec
    return obj


def thaw(obj: Any) -> Any:
    """Recursively convert persistent collections back to plain Python equivalents.

    - ``PersistentMap`` -> ``dict`` (values recursively thawed)
    - ``PersistentVector`` -> ``list`` (elements recursively thawed)
    - All other values pass through unchanged.

    Usage::

        frozen_map = freeze({"a": [1, 2, 3]})
        thaw(frozen_map)  # {"a": [1, 2, 3]}
    """
    if isinstance(obj, PersistentMap):
        return {k: thaw(v) for k, v in obj.items()}
    if isinstance(obj, PersistentVector):
        return [thaw(item) for item in obj]
    return obj
