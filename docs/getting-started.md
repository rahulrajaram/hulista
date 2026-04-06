# Getting Started

## Install choices

Use the umbrella package when you want the full stack:

```bash
pip install hulista
```

The single public distribution still exposes focused module imports when you only need a subset:

```python
from persistent_collections import PersistentMap
from live_dispatch import Dispatcher
```

## What `hulista` re-exports

The umbrella package re-exports a curated subset of the most common APIs:

- `PersistentMap`, `PersistentVector`, `TransientMap`
- `Result`, `Ok`, `Err`, `pipe`, `async_pipe`, `async_try_pipe`
- `Actor`, `ActorRef`, `ActorSystem`
- `Dispatcher`
- `sealed`, `sealed_subclasses`
- `CollectorTaskGroup`
- `updatable`, `with_update`

## First composition

```python
import hulista


store = hulista.PersistentMap().set("count", 1)
updated = store.set("count", store["count"] + 1)

value = hulista.pipe(
    updated,
    lambda pm: pm["count"],
    lambda count: count * 10,
)

assert value == 20
```

## When to use focused imports

Choose focused imports instead of the `hulista` namespace if:

- your library only uses one concept and you want your imports to stay explicit
- you prefer importing `persistent_collections`, `live_dispatch`, or `with_update` directly in application code
- you want to keep your public API explicit about which hulista primitive you depend on

The `hulista` distribution itself requires Python 3.11 because some bundled modules do.

## Local docs workflow

```bash
python -m pip install -r docs/requirements.txt
make docs-serve
```

Use `make docs-build` before publishing docs changes to catch broken links or invalid markdown extensions.
