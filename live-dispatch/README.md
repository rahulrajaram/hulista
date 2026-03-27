# live-dispatch

Runtime-extensible dispatch — single dispatch, predicate dispatch, and versioned handler rollback. Agents and plugins can register handlers dynamically.

## Install

```
uv add live-dispatch
```

## Quick start

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

## API reference

### `Dispatcher(name="dispatcher")`

| Method | Signature | Description |
|---|---|---|
| `.register(func, *, priority=0)` | `(Callable) -> Callable` | Register handler (decorator or direct call) |
| `.fallback(func)` | `(Callable) -> Callable` | Register fallback for unmatched calls |
| `.unregister(func)` | `(Callable) -> None` | Remove a handler |
| `.clear()` | `() -> None` | Remove all handlers |
| `.handlers()` | `() -> list[dict]` | Introspect registered handlers |
| `dispatch(*args, **kw)` | `(*Any, **Any) -> Any` | Call the best matching handler |

### `predicate(condition)`

Decorator that attaches a predicate function to a handler. The predicate receives the same arguments as the dispatch call and must return `bool`.

### `versioned(dispatcher) -> VersionedContext`

Context manager that snapshots the handler list on entry. Call `.rollback()` inside to restore to the snapshot.

## Upstream context

`functools.singledispatch` provides static single dispatch. `live-dispatch` extends this with:
- **Multiple dispatch** on multiple argument types
- **Predicate dispatch** on runtime values
- **Dynamic registration** — handlers added/removed at runtime
- **Versioned rollback** — experiment with new handlers safely

## License

MIT
