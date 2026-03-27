# asyncio-actors

OTP-inspired actor primitives for Python's `asyncio` — bounded inboxes, hierarchical supervision trees, circuit breakers, selective receive, and an async-sync bridge.

## Install

```
uv add asyncio-actors
```

## Quick start

```python
import asyncio
from asyncio_actors import Actor, ActorSystem

class Greeter(Actor):
    async def on_message(self, name: str) -> str:
        return f"Hello, {name}!"

async def main():
    async with ActorSystem() as system:
        ref = await system.spawn(Greeter)
        reply = await ref.ask("world")
        print(reply)  # "Hello, world!"

asyncio.run(main())
```

### Hierarchical supervision

```python
from asyncio_actors import Supervisor, ChildSpec, SupervisorStrategy, RestartType

class WorkerA(Actor):
    async def on_message(self, msg): ...

class WorkerB(Actor):
    async def on_message(self, msg): ...

class MyApp(Supervisor):
    strategy = SupervisorStrategy.ONE_FOR_ONE
    children_specs = [
        ChildSpec(WorkerA),
        ChildSpec(WorkerB, restart=RestartType.TRANSIENT),
    ]
```

### Circuit breaker

```python
from asyncio_actors import CircuitBreaker
import time

breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)

if breaker.allow_request(time.monotonic()):
    try:
        result = call_external_service()
        breaker.record_success()
    except Exception:
        breaker.record_failure(time.monotonic())
```

## API reference

### Core classes

| Name | Description |
|---|---|
| `Actor` | Base class. Subclass and implement `on_message()`. |
| `ActorRef` | Handle for sending messages to an actor. |
| `ActorSystem` | Spawns and supervises actors (async context manager). |
| `Inbox` | Bounded message queue with configurable overflow. |
| `PersistentBridge` | Async-sync bridge for monitor-thread patterns. |
| `Supervisor` | Hierarchical supervision with configurable restart strategies. |
| `ChildSpec` | Specification for a child actor managed by a Supervisor. |
| `CircuitBreaker` | Failure isolation with CLOSED/OPEN/HALF_OPEN state machine. |

### `Actor` lifecycle hooks

| Hook | Signature | Called when |
|---|---|---|
| `on_start()` | `async () -> None` | Actor starts (once per run) |
| `on_message(msg)` | `async (Any) -> Any` | Each message received |
| `on_stop()` | `async () -> None` | Graceful shutdown |
| `on_error(exc)` | `async (Exception) -> SupervisionStrategy` | Unhandled error in `on_message` |

### `Actor` class attributes

| Attribute | Default | Description |
|---|---|---|
| `inbox_size` | `100` | Maximum inbox capacity |
| `overflow_policy` | `OverflowPolicy.BLOCK` | What to do when inbox is full |
| `restart_policy` | `RestartPolicy()` | Sliding-window restart limits (per-instance) |

### `ActorRef` methods

| Method | Signature | Description |
|---|---|---|
| `.send(msg)` | `async (Any) -> None` | Fire-and-forget delivery |
| `.ask(msg, timeout=5.0)` | `async (Any, float) -> Any` | Send and await reply |
| `.is_alive` | `bool` | Whether the actor is running |

### `Supervisor`

| Attribute | Type | Description |
|---|---|---|
| `strategy` | `SupervisorStrategy` | `ONE_FOR_ONE`, `ONE_FOR_ALL`, or `REST_FOR_ONE` |
| `children_specs` | `list[ChildSpec]` | Child actor specifications |

| Method | Description |
|---|---|
| `child_refs()` | Return `ActorRef` handles for all managed children |

### `ChildSpec(actor_cls, restart=RestartType.PERMANENT, args=(), kwargs={})`

| `RestartType` | Behavior |
|---|---|
| `PERMANENT` | Always restart on exit |
| `TRANSIENT` | Restart only on abnormal exit (crash) |
| `TEMPORARY` | Never restart |

### `SupervisorStrategy`

| Value | Behavior |
|---|---|
| `ONE_FOR_ONE` | Restart only the failed child |
| `ONE_FOR_ALL` | Restart all children when one fails |
| `REST_FOR_ONE` | Restart the failed child and all children started after it |

### `CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, half_open_max_calls=1)`

| Method | Signature | Description |
|---|---|---|
| `.allow_request(now)` | `(float) -> bool` | Check if a request is allowed |
| `.record_failure(now)` | `(float) -> None` | Record a failure |
| `.record_success()` | `() -> None` | Record a success |
| `.reset()` | `() -> None` | Reset to CLOSED state |
| `.state` | `CircuitState` | Current state: `CLOSED`, `OPEN`, or `HALF_OPEN` |

Raises `CircuitOpenError` when `allow_request()` returns `False`.

### `OverflowPolicy`

| Value | Behavior |
|---|---|
| `BLOCK` | Await until space available (event-based, no spin-wait) |
| `DROP_OLDEST` | Drop oldest message to make room |
| `RAISE` | Raise `InboxFull` immediately |

### `SupervisionStrategy` (per-message)

| Value | Behavior |
|---|---|
| `RESTART` | Continue the actor's run loop |
| `STOP` | Stop the actor permanently |
| `ESCALATE` | Propagate error to the system |

### `RestartPolicy(max_restarts=3, restart_window_seconds=60.0)`

Sliding-window rate limit on system-level restarts. After `max_restarts` within the window, the actor is permanently stopped. Each actor instance gets its own policy — no shared state between instances.

### Selective receive

```python
# Scan inbox for a specific message type, leaving non-matching messages
msg = await actor._inbox.receive(match=MyMessageType, timeout=5.0)
```

### `PersistentBridge(loop)`

| Method | Signature | Description |
|---|---|---|
| `.call(coro_func, *args)` | `(Callable, ...) -> None` | Fire-and-forget from sync thread |
| `.call_wait(coro_func, *args, timeout=None)` | `(Callable, ...) -> T` | Blocking call from sync thread |

### System-level restart behavior

When `ActorSystem` restarts a crashed actor:
- Buffered messages are drained from the old inbox into the new one (no message loss)
- Exponential backoff is applied between restarts (100ms initial, 5s max, 2x factor)

## Upstream context

Inspired by the Erlang/OTP actor and supervision model. Python's `asyncio` provides tasks and task groups but no built-in actor abstraction with:
- Bounded mailboxes (back-pressure)
- Hierarchical supervision trees
- Automatic restart with rate-limiting and exponential backoff
- `ask`/`send` message-passing patterns
- Circuit breaker for failure isolation

## License

MIT
