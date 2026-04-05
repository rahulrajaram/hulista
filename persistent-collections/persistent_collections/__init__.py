"""Persistent immutable collections with structural sharing."""
from persistent_collections.persistent_map import PersistentMap, TransientMap
from persistent_collections.persistent_vector import PersistentVector, TransientVector
from persistent_collections.persistent_set import PersistentSet
from persistent_collections._diff import diff, Change, ChangeType
from persistent_collections._paths import assoc_in, update_in, dissoc_in
from persistent_collections._freeze import freeze, thaw

__all__ = [
    "PersistentMap",
    "TransientMap",
    "PersistentVector",
    "TransientVector",
    "PersistentSet",
    "diff",
    "Change",
    "ChangeType",
    "assoc_in",
    "update_in",
    "dissoc_in",
    "freeze",
    "thaw",
]
