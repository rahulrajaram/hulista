# live-dispatch

Runtime-extensible dispatch with priority-ordered runtime type matching,
predicate dispatch, async dispatch, and versioned rollback. Agents and plugins
can register handlers dynamically.

## Install

```
uv add live-dispatch
```

## Quick start

`live-dispatch` is intentionally priority-ordered in v0.1.0. When multiple
handlers could match, the highest-priority registration wins; equal-priority
ties preserve registration order. It does not attempt specificity ranking.

### Single dispatch on type

```python
from live_dispatch import Dispatcher

dispatch = Dispatcher("process")

@dispatch.register
def handle_int(x: int) -> str:
    return f"integer: {x}"

@dispatch.register
def handle_str(x: str) -> str:
    return f"string: {x}"

dispatch(42)    # "integer: 42"
dispatch("hi")  # "string: hi"
```

### Predicate dispatch

```python
from live_dispatch import Dispatcher, predicate

dispatch = Dispatcher("route")

@dispatch.register(priority=10)
@predicate(lambda x: isinstance(x, int) and x > 100)
def handle_large(x: int) -> str:
    return "large"

@dispatch.register
def handle_int(x: int) -> str:
    return "normal"

dispatch(200)  # "large"  (predicate matches first — higher priority)
dispatch(5)    # "normal"
```

### Async dispatch

```python
import asyncio
from live_dispatch import Dispatcher

dispatch = Dispatcher("async_api")

@dispatch.register
async def handle_str(x: str) -> str:
    await asyncio.sleep(0.01)
    return f"async: {x}"

result = asyncio.run(dispatch.call_async("hello"))  # "async: hello"

`call_async()` awaits any awaitable return value, not just coroutine objects.
```

### Versioned rollback

```python
from live_dispatch import Dispatcher, versioned

dispatch = Dispatcher("api")

@dispatch.register
def v1_handler(x: str) -> str:
    return "v1"

with versioned(dispatch) as v:
    @dispatch.register(priority=10)
    def experimental(x: str) -> str:
        return "experimental"

    assert dispatch("test") == "experimental"
    v.rollback()  # restores to v1 only

assert dispatch("test") == "v1"
```

### Method combinations (CLOS-inspired)

```python
from live_dispatch import Dispatcher

dispatch = Dispatcher("process")

class Task:
    def __init__(self, name: str):
        self.name = name

@dispatch.register
def handle(task: Task) -> str:
    return f"done:{task.name}"

@dispatch.before(Task)
def log_start(task: Task) -> None:
    print(f"Starting: {task.name}")

@dispatch.after(Task)
def log_end(task: Task) -> None:
    print(f"Done: {task.name}")

@dispatch.around(Task)
def time_it(proceed, task: Task) -> str:
    import time
    t0 = time.time()
    result = proceed(task)
    print(f"Took {time.time() - t0:.3f}s")
    return result

dispatch(Task("build"))
# Prints: Starting: build → runs handle → Prints: Done: build
# time_it wraps the entire chain
```

Execution order: `:before` advisors run first (registration order), then the
primary handler, then `:after` advisors (reverse registration order). `:around`
advisors wrap the entire chain via a `proceed()` callback. When no advisors
match, dispatch takes the fast path with zero overhead.

### Traced execution

```python
result, trace = dispatch.call_traced(Task("deploy"))
for entry in trace:
    print(f"  {entry.phase}: {entry.name} ({entry.duration_ms:.1f}ms)")
```

`call_traced` and `call_async_traced` return `(result, list[CombinationTraceEntry])`
where each entry records `phase`, `name`, `duration_ms`, and `type_key`.

### Sealed type exhaustiveness checking

```python
from sealed_typing import sealed
from live_dispatch import Dispatcher

@sealed
class Event:
    pass

class Click(Event): pass
class Hover(Event): pass

dispatch = Dispatcher("events")

@dispatch.register
def on_click(e: Click): ...

# Raises TypeError listing missing: {Hover}
dispatch.verify_exhaustive(Event)

# Per-parameter checking
dispatch.verify_exhaustive(Event, param="e")

# Auto-discover all sealed types and verify each
dispatch.verify_all_sealed()
```

## API reference

### `Dispatcher(name="dispatcher")`

| Method | Signature | Description |
|---|---|---|
| `.register(func, *, priority=0)` | `(Callable) -> Callable` | Register handler (decorator or direct call) |
| `.fallback(func)` | `(Callable) -> Callable` | Register fallback for unmatched calls |
| `.before(type_key)` | `(type) -> decorator` | Register a :before advisor for a type |
| `.after(type_key)` | `(type) -> decorator` | Register an :after advisor for a type |
| `.around(type_key)` | `(type) -> decorator` | Register an :around advisor for a type |
| `.unregister(func)` | `(Callable) -> None` | Remove a handler and its advisors |
| `.clear()` | `() -> None` | Remove all handlers and advisors |
| `.handlers()` | `() -> list[dict]` | Introspect registered handlers |
| `dispatch(*args, **kw)` | `(*Any, **Any) -> Any` | Call the first matching handler by priority/order |
| `.call_traced(*args, **kw)` | `(*Any, **Any) -> (Any, list[CombinationTraceEntry])` | Dispatch with per-stage trace |
| `.call_async(*args, **kw)` | `async (*Any, **Any) -> Any` | Async dispatch |
| `.call_async_traced(*args, **kw)` | `async (*Any, **Any) -> (Any, list[CombinationTraceEntry])` | Async dispatch with trace |
| `.verify_exhaustive(sealed_base, *, param=None)` | `(type, *, str \| None) -> None` | Assert handlers cover all sealed subclasses |
| `.verify_exhaustive_for(sealed_base)` | `(type) -> None` | Check all parameters referencing a sealed hierarchy |
| `.verify_all_sealed()` | `() -> None` | Auto-discover sealed types and verify each |

### `CombinationTraceEntry`

NamedTuple with fields: `phase` (`"before"` | `"around"` | `"primary"` | `"after"`), `name` (str), `duration_ms` (float), `type_key` (type | None).

Handler registration only supports plain runtime classes in parameter
annotations. `typing.Any`, unions, generic aliases like `list[int]`, unresolved
forward references, and other non-runtime annotation forms raise `TypeError`
instead of silently becoming catch-alls.

Dispatch results are cached by argument type tuple for O(1) amortized dispatch
on repeated type signatures. The cache is automatically invalidated on
`register()`, `unregister()`, and `clear()`. Handlers with predicates bypass
the cache since they depend on argument values.

### `predicate(condition)`

Decorator that attaches a predicate function to a handler. The predicate receives the same arguments as the dispatch call and must return `bool`.

### `versioned(dispatcher) -> VersionedContext`

Context manager that snapshots handlers, fallback, cache, and predicate-cache
state on entry. Call `.rollback()` inside to restore that full dispatcher
state.

## Upstream context

`functools.singledispatch` provides static single dispatch. `live-dispatch`
extends this with:
- **Priority-ordered runtime dispatch** across one or more annotated arguments
- **Predicate dispatch** on runtime values
- **Async dispatch** for async handler functions
- **Dynamic registration** — handlers added/removed at runtime
- **Versioned rollback** — experiment with new handlers safely
- **Dispatch cache** — O(1) amortized dispatch on repeated type signatures
- **Sealed type integration** — verify exhaustive handler coverage

## License

MIT
