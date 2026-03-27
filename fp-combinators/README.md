# fp-combinators

Lightweight functional programming combinators for Python — `pipe`, `compose`, `first_some`, `pipeline`, `async_pipe`, and typed error handling with `Result`/`Ok`/`Err`.

## Install

```
uv add fp-combinators
```

## Quick start

```python
from fp_combinators import pipe, compose, first_some, pipeline, async_pipe
from fp_combinators import Result, Ok, Err, try_pipe

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

# Transparently handles both sync and async functions
result = asyncio.run(async_pipe("https://example.com", fetch, parse))
```

## API reference

| Function | Signature | Description |
|---|---|---|
| `pipe(value, *funcs)` | `(T, *Callable) -> R` | Thread value through functions left-to-right |
| `compose(*funcs)` | `(*Callable) -> Callable` | Compose functions right-to-left |
| `pipeline(*funcs)` | `(*Callable) -> Callable` | Create a left-to-right pipeline callable |
| `first_some(*funcs)` | `(*Callable[..., T\|None]) -> Callable[..., T\|None]` | Return first non-None result |
| `async_pipe(value, *funcs)` | `async (T, *Callable) -> R` | Thread value through sync/async functions |
| `try_pipe(value, *funcs)` | `(T, *Callable) -> Result[R, Exception]` | Error-aware pipeline |

### `Result[T, E]`

| Method | Signature | Description |
|---|---|---|
| `.is_ok()` | `() -> bool` | True if Ok |
| `.is_err()` | `() -> bool` | True if Err |
| `.unwrap()` | `() -> T` | Return value or raise |
| `.unwrap_or(default)` | `(T) -> T` | Return value or default |
| `.map(func)` | `(Callable[[T], U]) -> Result[U, E]` | Transform Ok value |
| `.map_err(func)` | `(Callable[[E], F]) -> Result[T, F]` | Transform Err value |
| `.and_then(func)` | `(Callable[[T], Result[U, E]]) -> Result[U, E]` | Chain operations |
| `.or_else(func)` | `(Callable[[E], Result[T, F]]) -> Result[T, F]` | Recover from errors |

All combinators set `__qualname__` on the returned callable for debuggability.

## Upstream context

PEP 638 proposed a pipe operator (`|>`) for Python. It was rejected, but the underlying need — threading data through transformations without deeply nested calls — remains. This package provides the same ergonomics as library functions.

- [PEP 638 — Syntactic Macros](https://peps.python.org/pep-0638/) (rejected)
- Related discussion: [python-ideas: pipe operator](https://discuss.python.org/t/pipe-operator/)

## License

MIT
