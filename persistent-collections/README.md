# persistent-collections

Immutable persistent collections with structural sharing — `PersistentMap` and `PersistentVector` backed by a pure-Python HAMT.

## Install

```
uv add persistent-collections
```

## Quick start

```python
from persistent_collections import PersistentMap, PersistentVector

# PersistentMap — immutable dict with O(log32 n) updates
m = PersistentMap(x=1, y=2, z=3)
m2 = m.set("x", 10)        # new map; m is unchanged
m3 = m2.delete("z")

assert m["x"] == 1          # original untouched
assert m2["x"] == 10
assert "z" not in m3

# PersistentVector — immutable list with O(log32 n) append/set
v = PersistentVector([1, 2, 3])
v2 = v.append(4)
v3 = v2.set(0, 99)

assert list(v) == [1, 2, 3]  # original untouched
assert list(v3) == [99, 2, 3, 4]
```

## API reference

### `PersistentMap`

| Method / Property | Signature | Description |
|---|---|---|
| `PersistentMap(**kw)` | `(**kwargs) -> PersistentMap` | Create from keyword arguments |
| `.from_dict(d)` | `(dict) -> PersistentMap` | Create from an existing dict |
| `.set(key, value)` | `(key, value) -> PersistentMap` | Return new map with key set |
| `.delete(key)` | `(key) -> PersistentMap` | Return new map without key |
| `.get(key, default)` | `(key, default=None) -> value` | Lookup with default |
| `m[key]` | — | Lookup (raises `KeyError`) |
| `len(m)` | — | Number of entries |
| `hash(m)` | — | Hashable (can be used as dict key / set member) |

### `PersistentVector`

| Method / Property | Signature | Description |
|---|---|---|
| `PersistentVector(iterable)` | `(iterable?) -> PersistentVector` | Create from iterable |
| `.append(value)` | `(value) -> PersistentVector` | Return new vector with value appended |
| `.set(index, value)` | `(int, value) -> PersistentVector` | Return new vector with element replaced |
| `v[i]`, `v[start:stop]` | — | Index and slice access |
| `v + other` | — | Concatenation (returns new vector) |
| `len(v)`, `hash(v)` | — | Length and hashability |

## Performance

The HAMT gives `PersistentMap.set()` O(log32 n) time and **structural sharing** — only the path from root to leaf is copied, not the entire tree.

Benchmark (1000 keys, 10000 updates via `benchmarks/bench_memory.py`):

| Operation | Time | Peak memory |
|---|---|---|
| `dict.copy()` + mutate | ~0.25 s | ~490 MB |
| `PersistentMap.set()` | ~0.60 s | ~27 MB |

**~18x memory reduction** at the cost of ~2.4x wall-clock time. For workloads with many snapshots (undo history, event sourcing, concurrent reads), persistent collections dominate.

## Upstream context

The HAMT algorithm mirrors CPython's internal `Python/hamt.c` (used by `contextvars`). This package exposes the data structure as a first-class collection for user code.

- CPython source: [`Python/hamt.c`](https://github.com/python/cpython/blob/main/Python/hamt.c)
- PEP 567 — Context Variables (uses HAMT internally)

## License

MIT
