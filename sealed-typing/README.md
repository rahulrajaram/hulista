# sealed-typing

Sealed classes for Python — restrict subclassing to the defining module, with runtime exhaustiveness checking for `match`/`case`.

## Install

```
uv add sealed-typing
```

## Quick start

```python
from sealed_typing import sealed, sealed_subclasses, assert_exhaustive

@sealed
class Shape:
    pass

class Circle(Shape):
    def __init__(self, radius: float):
        self.radius = radius

class Square(Shape):
    def __init__(self, side: float):
        self.side = side

# Attempting to subclass Shape from another module raises TypeError.

def area(shape: Shape) -> float:
    match shape:
        case Circle(radius=r):
            return 3.14159 * r * r
        case Square(side=s):
            return s * s
        case _:
            assert_exhaustive(shape, Circle, Square)
```

## API reference

| Function | Signature | Description |
|---|---|---|
| `@sealed` | `(cls: type) -> type` | Decorator — restricts subclassing to the same module |
| `is_sealed(cls)` | `(type) -> bool` | Check if a class is sealed |
| `sealed_subclasses(cls)` | `(type) -> frozenset[type]` | Return all registered subclasses |
| `assert_exhaustive(value, *handlers)` | `(Any, *type) -> None` | Raise `TypeError` if handlers don't cover all subclasses |

### How `@sealed` works

1. Marks the class with `__sealed__ = True`
2. Overrides `__init_subclass__` to reject subclasses from other modules
3. Tracks subclasses in `__sealed_subclasses__`

### `assert_exhaustive`

Walks the MRO to find the sealed base, compares provided handler types against `sealed_subclasses()`, and raises `TypeError` listing any missing cases.

## Upstream context

`typing.final` prevents all subclassing; `@sealed` allows controlled subclassing within a module — matching Kotlin's `sealed class` and Scala's `sealed trait`. This enables exhaustive pattern matching without losing the open/closed principle within a single module.

- [typing.final](https://docs.python.org/3/library/typing.html#typing.final) — related but stricter
- Kotlin sealed classes: [kotlinlang.org/docs/sealed-classes.html](https://kotlinlang.org/docs/sealed-classes.html)

## License

MIT
