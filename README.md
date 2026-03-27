# hulista

Functional programming and structured-concurrency building blocks for Python, born from real friction points in production agent orchestration.

## Packages

| Package | Description | Python |
|---|---|---|
| [persistent-collections](persistent-collections/) | Immutable HAMT-backed `PersistentMap` and `PersistentVector` with structural sharing, transient builders, and structural diffing | >= 3.10 |
| [sealed-typing](sealed-typing/) | `@sealed` classes with runtime exhaustiveness checking for `match`/`case` | >= 3.10 |
| [asyncio-actors](asyncio-actors/) | OTP-inspired actors with bounded inboxes, hierarchical supervision, circuit breakers, selective receive, and async-sync bridge | >= 3.11 |
| [taskgroup-collect](taskgroup-collect/) | `TaskGroup` variant that collects all errors instead of cancelling on first failure | >= 3.11 |
| [fp-combinators](fp-combinators/) | `pipe`, `compose`, `first_some`, `pipeline`, `async_pipe`, and `Result`/`Ok`/`Err` error handling | >= 3.10 |
| [live-dispatch](live-dispatch/) | Runtime-extensible dispatch: type dispatch, predicate dispatch, async dispatch, versioned rollback, and dispatch caching | >= 3.10 |
| [with-update](with-update/) | `\|` operator and `.with_update()` for frozen dataclasses and Pydantic models, with runtime field validation | >= 3.10 |

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
from persistent_collections import PersistentMap, TransientMap, diff
from sealed_typing import sealed
from with_update import updatable
from fp_combinators import pipe, Result, Ok, Err, try_pipe
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

# Error-aware pipelines with Result
result = try_pipe(
    "42",
    int,
    lambda x: x * 2,
)
assert result == Ok(84)

# Batch construction with transient builders
with PersistentMap().transient() as t:
    for i in range(1000):
        t[f"key_{i}"] = i
m = t.persistent()  # freeze to immutable

# Structural diffing
m2 = m.set("key_0", 999)
changes = list(diff(m, m2))  # O(changes), not O(n)
```

### Actor system with hierarchical supervision

```python
import asyncio
from asyncio_actors import (
    Actor, ActorSystem, Supervisor, ChildSpec,
    SupervisorStrategy, RestartType, CircuitBreaker,
)

class Worker(Actor):
    async def on_message(self, task: str) -> str:
        return f"processed: {task}"

class MyApp(Supervisor):
    strategy = SupervisorStrategy.ONE_FOR_ONE
    children_specs = [
        ChildSpec(Worker),
        ChildSpec(Worker, restart=RestartType.TRANSIENT),
    ]

async def main():
    async with ActorSystem() as system:
        ref = await system.spawn(Worker)
        reply = await ref.ask("hello")
        print(reply)  # "processed: hello"

asyncio.run(main())
```

## Architecture

The packages compose into a layered system:

```
  sealed-typing         Define message/event types with exhaustive matching
       |
  live-dispatch         Route messages to handlers (cached, async-aware)
       |
  fp-combinators        Thread data through pipelines (sync, async, error-aware)
       |
  asyncio-actors        Process messages in supervised actor trees
       |                  +-- Supervisor (OneForOne / OneForAll / RestForOne)
       |                  +-- CircuitBreaker (failure isolation)
       |                  +-- Selective receive (type-matched inbox scan)
       |
  taskgroup-collect     Fan out concurrent work, collect all results
       |
  persistent-collections + with-update
                        Accumulate immutable state with structural sharing
                          +-- TransientMap (batch construction)
                          +-- diff() (O(changes) structural diffing)
```

## Key features by package

### persistent-collections

- `PersistentMap` — immutable dict with O(log32 n) set/delete/get via HAMT
- `PersistentVector` — immutable list with O(log32 n) append/set
- `TransientMap` — mutable builder for batch construction, freezes back to `PersistentMap`
- `diff(m1, m2)` — structural diffing yielding `Change` objects (ADDED/REMOVED/MODIFIED)
- HAMT internals: `BitmapNode`, `ArrayNode` (dense 32-slot), `CollisionNode`
- XOR hash folding matching CPython's `Python/hamt.c` algorithm
- Hashable — maps and vectors can be used as dict keys or set members

### asyncio-actors

- `Actor` / `ActorRef` — base actor with inbox and lifecycle hooks (`on_start`, `on_message`, `on_stop`, `on_error`)
- `ActorSystem` — spawn and supervise actors with automatic restarts and exponential backoff
- `Supervisor` — hierarchical supervision with `OneForOne`, `OneForAll`, `RestForOne` strategies
- `ChildSpec` — child actor specification with `PERMANENT`, `TRANSIENT`, `TEMPORARY` restart types
- `CircuitBreaker` — failure isolation with CLOSED/OPEN/HALF_OPEN state machine
- Selective receive — `inbox.receive(match=type)` scans for type-matched messages
- `Inbox` — bounded queue with `BLOCK` (event-based, no spin-wait), `DROP_OLDEST`, `RAISE` overflow policies
- `PersistentBridge` — async-sync bridge for monitor-thread patterns
- Message preservation on actor restart (old inbox drained into new)

### fp-combinators

- `pipe(value, *funcs)` — thread value through functions left-to-right
- `compose(*funcs)` — compose functions right-to-left
- `pipeline(*funcs)` — create a reusable left-to-right callable
- `first_some(*funcs)` — short-circuit on first non-None result
- `async_pipe(value, *funcs)` — transparently handles sync and async functions
- `Result[T, E]` / `Ok(value)` / `Err(error)` — typed error handling without exceptions
- `try_pipe(value, *funcs)` — error-aware pipeline that catches exceptions into `Err`

### live-dispatch

- Type dispatch on argument types with priority ordering
- Predicate dispatch on runtime values
- Dispatch cache — O(1) amortized dispatch on repeated type signatures (auto-invalidated)
- `call_async()` — async dispatch support
- `verify_exhaustive(sealed_base)` — assert handlers cover all sealed subclasses
- `versioned(dispatcher)` — snapshot/rollback for safe experimentation
- Dynamic registration and unregistration at runtime

### with-update

- `@updatable` — adds `|` operator and `.with_update()` to frozen dataclasses and Pydantic models
- Runtime field validation — invalid field names in `|` raise `TypeError` with a clear message listing valid fields

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
