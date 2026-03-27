"""Runtime-extensible dispatch with multiple dispatch, predicate dispatch, and versioning."""
from live_dispatch._dispatcher import Dispatcher
from live_dispatch._predicate import predicate
from live_dispatch._versioned import versioned, VersionedContext

__all__ = ["Dispatcher", "predicate", "versioned", "VersionedContext"]
