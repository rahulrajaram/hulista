# hulista

Functional, immutable, concurrent Python — all batteries included.

This is the umbrella meta-package that installs all seven hulista libraries in one go:

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

```
pip install hulista
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

## Requires Python 3.11+
