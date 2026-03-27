# asyncio-actors

OTP-inspired actor primitives for Python's `asyncio` — bounded inboxes, supervision trees with automatic restarts, and an async-sync bridge.

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

## API reference

### Core classes

| Name | Description |
|---|---|
| `Actor` | Base class. Subclass and implement `on_message()`. |
| `ActorRef` | Handle for sending messages to an actor. |
| `ActorSystem` | Spawns and supervises actors (async context manager). |
| `Inbox` | Bounded message queue with configurable overflow. |
| `PersistentBridge` | Async-sync bridge for monitor-thread patterns. |

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
| `restart_policy` | `RestartPolicy()` | Sliding-window restart limits |

### `ActorRef` methods

| Method | Signature | Description |
|---|---|---|
| `.send(msg)` | `async (Any) -> None` | Fire-and-forget delivery |
| `.ask(msg, timeout=5.0)` | `async (Any, float) -> Any` | Send and await reply |
| `.is_alive` | `bool` | Whether the actor is running |

### `OverflowPolicy`

| Value | Behavior |
|---|---|
| `BLOCK` | Block sender until space available |
| `DROP_OLDEST` | Drop oldest message to make room |
| `RAISE` | Raise `InboxFull` immediately |

### `SupervisionStrategy`

| Value | Behavior |
|---|---|
| `RESTART` | Continue the actor's run loop |
| `STOP` | Stop the actor permanently |
| `ESCALATE` | Propagate error to the system |

### `RestartPolicy(max_restarts=3, restart_window_seconds=60.0)`

Sliding-window rate limit on system-level restarts. After `max_restarts` within the window, the actor is permanently stopped.

### `PersistentBridge(loop)`

| Method | Signature | Description |
|---|---|---|
| `.call(coro_func, *args)` | `(Callable, ...) -> None` | Fire-and-forget from sync thread |
| `.call_wait(coro_func, *args, timeout=None)` | `(Callable, ...) -> T` | Blocking call from sync thread |

## Upstream context

Inspired by the Erlang/OTP actor and supervision model. Python's `asyncio` provides tasks and task groups but no built-in actor abstraction with:
- Bounded mailboxes (back-pressure)
- Automatic restart with rate-limiting
- `ask`/`send` message-passing patterns

## License

MIT
