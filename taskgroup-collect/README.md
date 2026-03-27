# taskgroup-collect

A `TaskGroup` variant that runs **all** tasks to completion and collects errors, instead of cancelling siblings on the first failure.

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

## API reference

| Name | Signature | Description |
|---|---|---|
| `CollectorTaskGroup()` | `() -> CollectorTaskGroup` | Create a collector group |
| `.create_task(coro)` | `(coro, **kw) -> asyncio.Task` | Spawn a task in the group |
| `async with ... as tg:` | — | Context manager; raises `BaseExceptionGroup` on exit if any task failed |

External cancellation of the parent task still propagates to children normally — only the abort-on-first-error behavior is changed.

## Upstream context

- CPython issue: [#101581 — TaskGroup should optionally not cancel on first error](https://github.com/python/cpython/issues/101581)
- The stdlib `TaskGroup` (PEP 654) intentionally cancels siblings. This package provides the complementary "collect all" semantics requested in the issue.

## License

MIT
