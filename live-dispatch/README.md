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
```

## API reference

### `Dispatcher(name="dispatcher")`

| Method | Signature | Description |
|---|---|---|
| `.register(func, *, priority=0)` | `(Callable) -> Callable` | Register handler (decorator or direct call) |
| `.fallback(func)` | `(Callable) -> Callable` | Register fallback for unmatched calls |
| `.unregister(func)` | `(Callable) -> None` | Remove a handler |
| `.clear()` | `() -> None` | Remove all handlers |
| `.handlers()` | `() -> list[dict]` | Introspect registered handlers |
| `dispatch(*args, **kw)` | `(*Any, **Any) -> Any` | Call the first matching handler by priority/order |
| `.call_async(*args, **kw)` | `async (*Any, **Any) -> Any` | Async dispatch |
| `.verify_exhaustive(sealed_base)` | `(type) -> None` | Assert handlers cover all sealed subclasses |

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
