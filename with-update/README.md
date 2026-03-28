# with-update

Copy-update syntax for dataclasses and Pydantic models — the `|` operator and
`.with_update()` method so you do not need raw `dataclasses.replace()` or
hand-rolled model-copy helpers. Includes runtime field validation.

## Install

```
uv add with-update
```

## Quick start

```python
from dataclasses import dataclass
from with_update import updatable

@updatable
@dataclass(frozen=True)
class Config:
    host: str = "localhost"
    port: int = 8080
    debug: bool = False

cfg = Config()
cfg2 = cfg | {"port": 9090, "debug": True}
cfg3 = cfg.with_update(host="0.0.0.0")

assert cfg.port == 8080       # original unchanged
assert cfg2.port == 9090
assert cfg3.host == "0.0.0.0"
```

### Contrast with `dataclasses.replace()`

```python
# Without with-update:
new = dataclasses.replace(cfg, port=9090, debug=True)

# With with-update — same result, cleaner syntax:
new = cfg | {"port": 9090, "debug": True}
new = cfg.with_update(port=9090, debug=True)
```

## API reference

| Name | Signature | Description |
|---|---|---|
| `@updatable` | `(cls: type) -> type` | Decorator — adds `__or__` and `with_update` to a dataclass or Pydantic model |
| `with_update(obj, **changes)` | `(obj, **Any) -> obj` | Standalone function — works on any dataclass or Pydantic model instance |

### `@updatable` adds

| Method | Signature | Description |
|---|---|---|
| `obj \| dict` | `(dict) -> Self` | Return new instance with fields from dict applied |
| `.with_update(**kw)` | `(**Any) -> Self` | Return new instance with keyword fields applied |

Works with dataclasses and Pydantic `BaseModel` subclasses. For Pydantic v2,
updates are validated, alias-aware, and preserve private attrs plus
`model_fields_set`.

### Runtime field validation

The `|` operator validates field names at runtime. Invalid fields raise `TypeError` with a clear message:

```python
cfg = Config()
cfg | {"nonexistent": 42}
# TypeError: Invalid field(s) for Config: nonexistent. Valid fields: debug, host, port
```

## Upstream context

`dataclasses.replace()` works but reads poorly when chained or nested. The `|`
operator mirrors `dict | dict` (PEP 584) and provides the same ergonomics for
copy-update workflows on record-like objects.

- [PEP 584 — Add Union Operators To dict](https://peps.python.org/pep-0584/)
- [dataclasses.replace()](https://docs.python.org/3/library/dataclasses.html#dataclasses.replace)

## License

MIT
