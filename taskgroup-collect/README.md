# taskgroup-collect

A `TaskGroup` variant that runs **all** tasks to completion and collects errors,
instead of cancelling siblings on the first failure.

## Install

```
uv add taskgroup-collect
```

## Quick start

```python
import asyncio
from taskgroup_collect import CollectorTaskGroup

async def main():
    async with CollectorTaskGroup() as tg:
        t1 = tg.create_task(fetch("https://a.example.com"))
        t2 = tg.create_task(fetch("https://b.example.com"))
        t3 = tg.create_task(fetch("https://c.example.com"))

    # All three ran to completion — even if one raised.
    # Successes are available via t1.result(), t2.result(), etc.
    # If any failed, a BaseExceptionGroup is raised on exit.

asyncio.run(main())
```

### Contrast with stdlib `TaskGroup`

```python
# stdlib — cancels t2/t3 when t1 raises
async with asyncio.TaskGroup() as tg:
    t1 = tg.create_task(flaky())   # raises
    t2 = tg.create_task(slow_ok()) # cancelled!
    t3 = tg.create_task(slow_ok()) # cancelled!

# taskgroup-collect — all three finish
async with CollectorTaskGroup() as tg:
    t1 = tg.create_task(flaky())   # raises
    t2 = tg.create_task(slow_ok()) # completes
    t3 = tg.create_task(slow_ok()) # completes
# BaseExceptionGroup with t1's error; t2/t3 results available
```

There is one more semantic difference from stdlib `TaskGroup`: if a child task
fails while the `async with` body is still running, the body continues to run
until it exits normally or raises on its own. You can even create more tasks in
that same block after an earlier child has already failed. Errors are still
collected and raised on exit.

## API reference

| Name | Signature | Description |
|---|---|---|
| `CollectorTaskGroup(*, limit=None)` | `(*, int \| None) -> CollectorTaskGroup` | Create a collector group with optional concurrency limit |
| `.create_task(coro)` | `(coro, **kw) -> asyncio.Task` | Spawn a task in the group |
| `.outcomes()` | `() -> list[TaskOutcome]` | Per-task `Success`/`Failure` outcomes in creation order (call after exit) |
| `async with ... as tg:` | — | Context manager; raises `BaseExceptionGroup` on exit if any task failed |
| `collect_results(coros, *, limit=None)` | `async (Iterable[Coroutine], *, int \| None) -> list[TaskOutcome]` | Convenience wrapper — run coroutines concurrently, return outcomes (never raises) |
| `outcome_to_result(outcome)` | `(TaskOutcome[T]) -> Result[T, BaseException]` | Convert `TaskOutcome` to fp-combinators `Result` (requires fp-combinators) |
| `result_to_outcome(result)` | `(Result[T, E]) -> TaskOutcome[T]` | Convert fp-combinators `Result` to `TaskOutcome` (Err must be BaseException) |
| `outcomes_to_results(outcomes)` | `(Iterable[TaskOutcome]) -> list[Result]` | Bulk convert outcomes to Results |

External cancellation of the parent task still propagates to children normally.
Compared with stdlib `TaskGroup`, this package changes two things:
- sibling tasks are not cancelled on child failure
- child failure does not interrupt the active `async with` body

Two more details are important:
- a child that ends with `CancelledError` is treated as cancelled, not collected
- `KeyboardInterrupt` and `SystemExit` win over ordinary error aggregation

## Upstream context

- CPython issue: [#101581 — TaskGroup should optionally not cancel on first error](https://github.com/python/cpython/issues/101581)
- The stdlib `TaskGroup` (PEP 654) intentionally cancels siblings. This package provides the complementary "collect all" semantics requested in the issue.

## License

MIT
