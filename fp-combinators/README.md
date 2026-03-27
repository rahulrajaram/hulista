# fp-combinators

Lightweight functional programming combinators for Python — `pipe`, `compose`, `first_some`, and `pipeline`.

## Install

```
uv add fp-combinators
```

## Quick start

```python
from fp_combinators import pipe, compose, first_some, pipeline

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

## API reference

| Function | Signature | Description |
|---|---|---|
| `pipe(value, *funcs)` | `(T, *Callable) -> R` | Thread value through functions left-to-right |
| `compose(*funcs)` | `(*Callable) -> Callable` | Compose functions right-to-left |
| `pipeline(*funcs)` | `(*Callable) -> Callable` | Create a left-to-right pipeline callable |
| `first_some(*funcs)` | `(*Callable[..., T\|None]) -> Callable[..., T\|None]` | Return first non-None result |

All combinators set `__qualname__` on the returned callable for debuggability.

## Upstream context

PEP 638 proposed a pipe operator (`|>`) for Python. It was rejected, but the underlying need — threading data through transformations without deeply nested calls — remains. This package provides the same ergonomics as library functions.

- [PEP 638 — Syntactic Macros](https://peps.python.org/pep-0638/) (rejected)
- Related discussion: [python-ideas: pipe operator](https://discuss.python.org/t/pipe-operator/)

## License

MIT
