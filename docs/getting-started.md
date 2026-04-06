# Getting Started

## Install choices

Use the umbrella package when you want the full stack:

```bash
pip install hulista
```

Use individual packages when you only need a subset:

```bash
pip install persistent-collections live-dispatch
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

## When to pick individual packages

Choose a focused package instead of `hulista` if:

- your library only needs one concept and you want minimal dependency surface
- you need Python 3.10 support for a package that does not require 3.11
- you want to keep your public API explicit about which hulista primitive you depend on

The umbrella package itself requires Python 3.11 because some bundled packages do.

## Local docs workflow

```bash
python -m pip install -r docs/requirements.txt
make docs-serve
```

Use `make docs-build` before publishing docs changes to catch broken links or invalid markdown extensions.
