# hulista

<div class="hero">
  <p class="hero-kicker">Python building blocks for immutable state, typed control flow, and structured concurrency.</p>
  <h1>Functional, immutable, concurrent Python that composes.</h1>
  <p class="hero-copy">
    hulista packages fill real stdlib gaps: persistent collections, sealed hierarchies,
    collect-all task groups, runtime dispatch, actor supervision, and ergonomic immutable updates.
  </p>
  <div class="hero-actions">
    <a class="md-button md-button--primary" href="getting-started/">Get started</a>
    <a class="md-button" href="packages/">Explore packages</a>
  </div>
</div>

## Why hulista?

- Persistent immutable collections are still awkward in Python when state changes frequently.
- `asyncio` gives you tasks, but not OTP-style supervision or collect-all structured concurrency.
- Python has excellent typing primitives, but not sealed class workflows for exhaustive branching.
- Runtime-extensible dispatch and record-update ergonomics are common needs in event-driven systems.

hulista takes those rough edges seriously and keeps the pieces small enough to adopt independently.

## Install

Install the umbrella package:

```bash
pip install hulista
```

The single `hulista` distribution still lets you import only the pieces you need:

```python
from persistent_collections import PersistentMap
from sealed_typing import sealed
from taskgroup_collect import CollectorTaskGroup
```

## Quick example

```python
from dataclasses import dataclass, field

import hulista


@hulista.sealed
class Command:
    pass


class Rename(Command):
    def __init__(self, value: str) -> None:
        self.value = value


@hulista.updatable
@dataclass(frozen=True)
class State:
    name: str = "guest"
    audit: hulista.PersistentVector = field(default_factory=hulista.PersistentVector)


def apply(state: State, command: Command) -> State:
    match command:
        case Rename(value=value):
            return state | {
                "name": value,
                "audit": state.audit.append(f"rename:{value}"),
            }


next_state = apply(State(), Rename("rahul"))
assert next_state.name == "rahul"
```

## Package family

<div class="package-grid">
  <a class="package-card" href="packages/#persistent-collections">
    <strong>persistent-collections</strong>
    <span>Immutable maps and vectors with structural sharing.</span>
  </a>
  <a class="package-card" href="packages/#sealed-typing">
    <strong>sealed-typing</strong>
    <span>Closed hierarchies for exhaustive branching and dispatch coverage.</span>
  </a>
  <a class="package-card" href="packages/#asyncio-actors">
    <strong>asyncio-actors</strong>
    <span>Supervised async actors, bounded inboxes, and bridges.</span>
  </a>
  <a class="package-card" href="packages/#taskgroup-collect">
    <strong>taskgroup-collect</strong>
    <span>Structured concurrency that gathers all results and failures.</span>
  </a>
  <a class="package-card" href="packages/#fp-combinators">
    <strong>fp-combinators</strong>
    <span>Small pipeline, Result, and traversal helpers for clearer control flow.</span>
  </a>
  <a class="package-card" href="packages/#live-dispatch">
    <strong>live-dispatch</strong>
    <span>Dynamic multiple dispatch with rollback and async support.</span>
  </a>
  <a class="package-card" href="packages/#with-update">
    <strong>with-update</strong>
    <span>Record-update syntax for frozen dataclasses and Pydantic models.</span>
  </a>
</div>

## Release surface

- The public docs site is published from this `docs/` directory with GitHub Pages.
- PyPI publishing is automated by GitHub Actions with Trusted Publishing.
- The release checklist lives in [`RELEASING.md`](https://github.com/rahulrajaram/hulista/blob/master/RELEASING.md).
