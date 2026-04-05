"""Runtime-extensible dispatch with multiple dispatch, predicate dispatch, and versioning."""
from live_dispatch._combinations import CombinationTraceEntry
from live_dispatch._dispatcher import AmbiguousDispatchError, Dispatcher
from live_dispatch._predicate import predicate
from live_dispatch._versioned import versioned, VersionedContext

__all__ = [
    "AmbiguousDispatchError",
    "CombinationTraceEntry",
    "Dispatcher",
    "predicate",
    "versioned",
    "VersionedContext",
]
