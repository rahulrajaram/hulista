# hulista

Functional programming and structured-concurrency building blocks for Python, born from real friction points in production agent orchestration.

## Packages

| Package | Description | Python |
|---|---|---|
| [persistent-collections](persistent-collections/) | Immutable HAMT-backed `PersistentMap` and `PersistentVector` with structural sharing | >= 3.10 |
| [sealed-typing](sealed-typing/) | `@sealed` classes with runtime exhaustiveness checking for `match`/`case` | >= 3.10 |
| [asyncio-actors](asyncio-actors/) | OTP-inspired actors with bounded inboxes, supervision trees, and async-sync bridge | >= 3.11 |
| [taskgroup-collect](taskgroup-collect/) | `TaskGroup` variant that collects all errors instead of cancelling on first failure | >= 3.11 |
| [fp-combinators](fp-combinators/) | `pipe`, `compose`, `first_some`, `pipeline` — lightweight FP combinators | >= 3.10 |
| [live-dispatch](live-dispatch/) | Runtime-extensible dispatch: type dispatch, predicate dispatch, versioned rollback | >= 3.10 |
| [with-update](with-update/) | `\|` operator and `.with_update()` for frozen dataclasses and Pydantic models | >= 3.10 |

## Motivation

These packages address gaps in the Python stdlib where production agent systems hit real friction:

- **No persistent collections** — `dict.copy()` is O(n) and memory-heavy; HAMTs give O(log32 n) with structural sharing
- **No sealed types** — `typing.final` prevents all subclassing; sealed classes allow controlled subclassing within a module for exhaustive matching
- **No actor model** — `asyncio` provides tasks but no bounded mailboxes, supervision, or ask/send patterns
- **No collect-all TaskGroup** — stdlib `TaskGroup` cancels siblings on first error; sometimes you need all results
- **No pipe/compose** — PEP 638 was rejected but the need remains
- **No runtime dispatch extensibility** — `functools.singledispatch` is static; agents need dynamic handler registration
- **No record update syntax** — `dataclasses.replace()` is verbose; `|` mirrors `dict | dict` (PEP 584)

Strategy: **PyPI first, PEP later** — the same path `attrs` took before `dataclasses` was added to the stdlib.

## Quick start

```python
from persistent_collections import PersistentMap
from sealed_typing import sealed
from with_update import updatable
from dataclasses import dataclass, field

# Immutable app state with sealed message types
@sealed
class Action:
    pass

class SetUser(Action):
    def __init__(self, name: str):
        self.name = name

class IncrCounter(Action):
    def __init__(self, amount: int):
        self.amount = amount

@updatable
@dataclass(frozen=True)
class State:
    user: str = ""
    counter: int = 0
    history: PersistentMap = field(default_factory=PersistentMap)

def reduce(state: State, action: Action) -> State:
    match action:
        case SetUser(name=n):
            return state | {"user": n}
        case IncrCounter(amount=a):
            return state | {"counter": state.counter + a}
```

## Architecture

The packages compose into a layered system:

```
  sealed-typing         Define message/event types with exhaustive matching
       |
  live-dispatch         Route messages to handlers dynamically
       |
  fp-combinators        Thread data through processing pipelines
       |
  asyncio-actors        Process messages in supervised actor loops
       |
  taskgroup-collect     Fan out concurrent work, collect all results
       |
  persistent-collections + with-update
                        Accumulate immutable state with structural sharing
```

## Upstream references

| Package | CPython issue / PEP |
|---|---|
| persistent-collections | `Python/hamt.c`, PEP 567 (contextvars) |
| sealed-typing | `typing.final`, Kotlin sealed classes |
| asyncio-actors | Erlang/OTP supervision model |
| taskgroup-collect | [#101581](https://github.com/python/cpython/issues/101581) |
| fp-combinators | PEP 638 (rejected pipe operator) |
| live-dispatch | `functools.singledispatch` |
| with-update | PEP 584 (`dict \| dict`) |

## Development

```bash
# Run all unit tests
for d in */; do
  if [ -d "$d/tests" ]; then
    (cd "$d" && python3 -m pytest tests/ -v)
  fi
done

# Run integration tests
python3 -m pytest tests/ -v
```

## License

MIT
