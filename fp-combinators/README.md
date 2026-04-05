# fp-combinators

Lightweight functional programming combinators for Python — `pipe`, `compose`, `first_some`, `pipeline`, `when`, `traced_pipe`, `resilient_pipe`, `async_pipe`, `async_traced_pipe`, `async_resilient_pipe`, `try_pipe`, `async_try_pipe`, and typed error handling with `Result`/`Ok`/`Err`.

## Install

```
uv add fp-combinators
```

## Quick start

```python
from fp_combinators import pipe, compose, first_some, pipeline, async_pipe
from fp_combinators import Result, Ok, Err, try_pipe, async_try_pipe

# pipe: thread a value left-to-right
result = pipe(
    "  Hello, World!  ",
    str.strip,
    str.lower,
    lambda s: s.replace(",", ""),
)
assert result == "hello world!"

# pipeline: create a reusable left-to-right callable
clean = pipeline(str.strip, str.lower)
assert clean("  HI  ") == "hi"

# compose: right-to-left (mathematical order)
add1_then_double = compose(lambda x: x * 2, lambda x: x + 1)
assert add1_then_double(3) == 8  # (3+1)*2

# first_some: short-circuit on first non-None
lookup = first_some(
    lambda k: {"a": 1}.get(k),
    lambda k: {"b": 2}.get(k),
    lambda k: 0,  # default
)
assert lookup("b") == 2
assert lookup("z") == 0
```

### Error handling with Result

```python
from fp_combinators import Ok, Err, try_pipe

# Explicit Result values
ok = Ok(42)
assert ok.is_ok()
assert ok.unwrap() == 42
assert ok.map(lambda x: x * 2) == Ok(84)

err = Err("missing")
assert err.is_err()
assert err.unwrap_or(0) == 0

# Monadic chaining
result = Ok(10).and_then(lambda x: Ok(x * 2) if x > 5 else Err("too small"))
assert result == Ok(20)

# Error-aware pipeline — catches exceptions into Err
result = try_pipe("42", int, lambda x: x * 2)
assert result == Ok(84)

result = try_pipe("not_a_number", int, lambda x: x * 2)
assert result.is_err()
```

### Async pipelines

```python
import asyncio
from fp_combinators import async_pipe

async def fetch(url: str) -> str:
    return f"data from {url}"

def parse(data: str) -> dict:
    return {"raw": data}

# Transparently handles both sync functions and any awaitable result
result = asyncio.run(async_pipe("https://example.com", fetch, parse))

async def validate(data: dict) -> dict:
    return data

safe = asyncio.run(async_try_pipe("https://example.com", fetch, parse, validate))
assert safe == Ok({"raw": "data from https://example.com"})
```

### Guarded, traced, and fail-soft stages

```python
from fp_combinators import resilient_pipe, traced_pipe, when

events = []

def record_error(stage, exc, value):
    events.append((stage.__name__, str(exc), value))
    return value

result = resilient_pipe(
    "  hello  ",
    str.strip,
    when(lambda s: bool(s), str.upper),
    lambda s: (_ for _ in ()).throw(ValueError("boom")),
    lambda s: f"{s}!",
    on_error=record_error,
)
assert result == "HELLO!"
assert events == [("<lambda>", "boom", "HELLO")]

final_value, trace = traced_pipe("  hello  ", str.strip, str.upper)
assert final_value == "HELLO"
assert trace[0].name == "strip"
```

## API reference

| Function | Signature | Description |
|---|---|---|
| `pipe(value, *funcs)` | `(T, *Callable) -> R` | Thread value through functions left-to-right |
| `compose(*funcs)` | `(*Callable) -> Callable` | Compose functions right-to-left |
| `pipeline(*funcs)` | `(*Callable) -> Callable` | Create a left-to-right pipeline callable |
| `when(predicate, fn)` | `(Callable[[T], bool], Callable[[T], U]) -> Callable[[T], T \| U]` | Apply `fn` only when `predicate(value)` is truthy |
| `traced_pipe(value, *funcs)` | `(T, *Callable) -> tuple[R, list[TraceEntry]]` | Run a pipeline and capture per-stage trace entries |
| `resilient_pipe(value, *funcs, on_error=...)` | `(T, *Callable) -> R` | Continue past stage failures using the last good value or callback replacement |
| `first_some(*funcs)` | `(*Callable[..., T\|None]) -> Callable[..., T\|None]` | Return first non-None result |
| `async_pipe(value, *funcs)` | `async (T, *Callable) -> R` | Thread value through sync/async functions |
| `async_traced_pipe(value, *funcs)` | `async (T, *Callable) -> tuple[R, list[TraceEntry]]` | Async trace-aware pipeline |
| `async_resilient_pipe(value, *funcs, on_error=...)` | `async (T, *Callable) -> R` | Async fail-soft pipeline |
| `try_pipe(value, *funcs)` | `(T, *Callable) -> Result[R, Exception]` | Error-aware pipeline |
| `async_try_pipe(value, *funcs)` | `async (T, *Callable) -> Result[R, Exception]` | Async error-aware pipeline |

### `Result[T, E]`

| Method | Signature | Description |
|---|---|---|
| `.is_ok()` | `() -> bool` | True if Ok |
| `.is_err()` | `() -> bool` | True if Err |
| `.unwrap()` | `() -> T` | Return value or raise |
| `.unwrap_or(default)` | `(T) -> T` | Return value or default |
| `.unwrap_err()` | `() -> E` | Return error or raise |
| `.map(func)` | `(Callable[[T], U]) -> Result[U, E]` | Transform Ok value |
| `.map_err(func)` | `(Callable[[E], F]) -> Result[T, F]` | Transform Err value |
| `.and_then(func)` | `(Callable[[T], Result[U, E]]) -> Result[U, E]` | Chain operations |
| `.or_else(func)` | `(Callable[[E], Result[T, F]]) -> Result[T, F]` | Recover from errors |

All combinators set `__qualname__` on the returned callable for debuggability.

Async helpers await any awaitable result, including coroutine objects,
`asyncio.Future`, `asyncio.Task`, and custom objects that implement
`__await__()`.

### Batch Result helpers

| Function | Signature | Description |
|---|---|---|
| `sequence(results)` | `(Iterable[Result[T, E]]) -> Result[list[T], E]` | Collect `Ok` values or return the first `Err` |
| `traverse(items, func)` | `(Iterable[T], Callable[[T], Result[U, E]]) -> Result[list[U], E]` | Map a Result-returning function over items, short-circuiting on first `Err` |
| `traverse_all(items, func)` | `(Iterable[T], Callable[[T], Result[U, E]]) -> Result[list[U], list[E]]` | Process every item and collect all error payloads |
| `async_sequence(results)` | `async (Iterable[Awaitable[Result[T, E]]]) -> Result[list[T], E]` | Sequential async collect — awaits one at a time, short-circuits on first `Err` |
| `async_traverse(items, func)` | `async (Iterable[T], async T -> Result[U, E]) -> Result[list[U], E]` | Sequential async map, short-circuits on first `Err` |
| `async_traverse_all(items, func)` | `async (Iterable[T], async T -> Result[U, E]) -> Result[list[U], list[E]]` | Sequential async map, collects all errors |

For concurrent/parallel fan-out, use [`taskgroup-collect`](../taskgroup-collect/) instead.

## License

MIT
