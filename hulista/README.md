# hulista

Functional, immutable, concurrent Python — all batteries included.

`hulista` is the single published distribution for the full hulista toolkit. One install gives you immutable data structures, sealed typing, runtime dispatch, actor-style concurrency, collect-all task groups, functional combinators, and record-update ergonomics.

Documentation: <https://rahulrajaram.github.io/hulista/>

## Why install the umbrella package?

Install `hulista` when you want a coherent batteries-included stack instead of picking packages one by one. It is especially useful for:

- event-driven or agent-style systems that combine immutable state with async orchestration
- teams that want one dependency and one docs entry point
- experimentation across the full package family before narrowing to individual imports

The `hulista` wheel bundles the toolkit's runtime modules directly:

| Package | Import | Description |
|---|---|---|
| asyncio-actors | `asyncio_actors` | OTP-inspired actor primitives for asyncio |
| fp-combinators | `fp_combinators` | Lightweight functional programming combinators |
| live-dispatch | `live_dispatch` | Runtime-extensible multiple dispatch |
| persistent-collections | `persistent_collections` | Immutable collections with structural sharing |
| sealed-typing | `sealed_typing` | Sealed classes for exhaustive matching |
| taskgroup-collect | `taskgroup_collect` | TaskGroup that collects all errors |
| with-update | `with_update` | Record update syntax for frozen dataclasses |

## Install

Install the full toolkit:

```bash
pip install hulista
```

The bundled modules remain importable directly if you prefer focused imports:

```python
from persistent_collections import PersistentMap
from fp_combinators import pipe
```

## Quick start

```python
import hulista

# Persistent immutable map
m = hulista.PersistentMap().set("x", 1).set("y", 2)

# FP pipe
result = hulista.pipe(m, lambda pm: sum(pm.values()))

# Result type
ok = hulista.Ok(42)
err = hulista.Err("oops")

# Sealed hierarchy
@hulista.sealed
class Event: pass

class Click(Event): pass
class KeyPress(Event): pass

subs = hulista.sealed_subclasses(Event)  # {Click, KeyPress}
```

## What you get

- `PersistentMap` / `PersistentVector` for immutable application state with structural sharing
- `pipe`, `async_pipe`, `Ok`, and `Err` for dataflow and typed error handling
- `ActorSystem` for supervised async workers and message passing
- `Dispatcher` for runtime-extensible type or predicate dispatch
- `sealed` for exhaustiveness-friendly closed hierarchies
- `CollectorTaskGroup` for collect-all structured concurrency
- `updatable` and `with_update` for record-update syntax on frozen models

## Source layout

Each package lives in the monorepo with its own README and tests, but the public PyPI release is `hulista`:

- [`asyncio-actors/`](https://github.com/rahulrajaram/hulista/tree/master/asyncio-actors)
- [`fp-combinators/`](https://github.com/rahulrajaram/hulista/tree/master/fp-combinators)
- [`live-dispatch/`](https://github.com/rahulrajaram/hulista/tree/master/live-dispatch)
- [`persistent-collections/`](https://github.com/rahulrajaram/hulista/tree/master/persistent-collections)
- [`sealed-typing/`](https://github.com/rahulrajaram/hulista/tree/master/sealed-typing)
- [`taskgroup-collect/`](https://github.com/rahulrajaram/hulista/tree/master/taskgroup-collect)
- [`with-update/`](https://github.com/rahulrajaram/hulista/tree/master/with-update)

## Requires Python 3.11+
