"""hulista — Functional, immutable, concurrent Python: all batteries included.

Re-exports the most commonly used public APIs from all seven hulista packages:

- persistent-collections: PersistentMap, PersistentVector, TransientMap
- fp-combinators:         Result, Ok, Err, pipe, async_pipe, async_try_pipe
- asyncio-actors:         Actor, ActorRef, ActorSystem
- live-dispatch:          Dispatcher
- sealed-typing:          sealed, sealed_subclasses
- taskgroup-collect:      CollectorTaskGroup
- with-update:            updatable, with_update
"""

# Persistent collections
from persistent_collections import PersistentMap, PersistentVector, TransientMap

# FP combinators
from fp_combinators import Result, Ok, Err, pipe, async_pipe, async_try_pipe

# Actors
from asyncio_actors import Actor, ActorRef, ActorSystem

# Dispatch
from live_dispatch import Dispatcher

# Sealed typing
from sealed_typing import sealed, sealed_subclasses

# Task groups
from taskgroup_collect import CollectorTaskGroup

# Updatable records
from with_update import updatable, with_update

__version__ = "0.1.0"

__all__ = [
    # persistent-collections
    "PersistentMap",
    "PersistentVector",
    "TransientMap",
    # fp-combinators
    "Result",
    "Ok",
    "Err",
    "pipe",
    "async_pipe",
    "async_try_pipe",
    # asyncio-actors
    "Actor",
    "ActorRef",
    "ActorSystem",
    # live-dispatch
    "Dispatcher",
    # sealed-typing
    "sealed",
    "sealed_subclasses",
    # taskgroup-collect
    "CollectorTaskGroup",
    # with-update
    "updatable",
    "with_update",
    # version
    "__version__",
]
