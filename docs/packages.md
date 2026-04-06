# Package Guide

## persistent-collections

- Import: `persistent_collections`
- Python: `>=3.10`
- Best for: immutable state, structural sharing, efficient diffs, transient batch updates
- Source: <https://github.com/rahulrajaram/hulista/tree/master/persistent-collections>

Key types:

- `PersistentMap`
- `PersistentVector`
- `TransientMap`
- `diff()`
- `freeze()` / `thaw()`

## sealed-typing

- Import: `sealed_typing`
- Python: `>=3.10`
- Best for: closed hierarchies, exhaustiveness checks, cleaner `match` workflows
- Source: <https://github.com/rahulrajaram/hulista/tree/master/sealed-typing>

Key APIs:

- `@sealed`
- `sealed_subclasses()`
- `verify_dispatch_exhaustive()`

## asyncio-actors

- Import: `asyncio_actors`
- Python: `>=3.11`
- Best for: supervised worker trees, inbox policies, ask/send patterns, async-sync bridges
- Source: <https://github.com/rahulrajaram/hulista/tree/master/asyncio-actors>

Key types:

- `Actor`
- `ActorRef`
- `ActorSystem`
- `Supervisor`
- `ChildSpec`
- `CircuitBreaker`

## taskgroup-collect

- Import: `taskgroup_collect`
- Python: `>=3.11`
- Best for: fan-out work that must collect all outcomes instead of failing fast
- Source: <https://github.com/rahulrajaram/hulista/tree/master/taskgroup-collect>

Key APIs:

- `CollectorTaskGroup`
- `collect_results()`
- `outcome_to_result()`
- `outcomes_to_results()`

## fp-combinators

- Import: `fp_combinators`
- Python: `>=3.10`
- Best for: value pipelines, async composition, typed Result flows
- Source: <https://github.com/rahulrajaram/hulista/tree/master/fp-combinators>

Key APIs:

- `pipe()`
- `compose()`
- `async_pipe()`
- `Result`, `Ok`, `Err`
- `try_pipe()`
- `traverse_all()`
- `async_traverse_all()`

## live-dispatch

- Import: `live_dispatch`
- Python: `>=3.10`
- Best for: runtime-extensible handler registration, type and predicate dispatch, reversible experimentation
- Source: <https://github.com/rahulrajaram/hulista/tree/master/live-dispatch>

Key APIs:

- `Dispatcher`
- `call_async()`
- `verify_exhaustive()`
- `versioned()`

## with-update

- Import: `with_update`
- Python: `>=3.10`
- Best for: ergonomic immutable updates on frozen dataclasses and Pydantic models
- Source: <https://github.com/rahulrajaram/hulista/tree/master/with-update>

Key APIs:

- `@updatable`
- `with_update()`
- `|`

## Choosing hulista

Install `hulista` when you want one dependency and one docs entry point. The bundled modules are still importable directly, but the public PyPI package is `hulista`.
