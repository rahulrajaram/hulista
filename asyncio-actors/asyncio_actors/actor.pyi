"""Type stubs for asyncio-actors."""
from __future__ import annotations

import asyncio
from typing import Any, Generic, TypeVar

from asyncio_actors.inbox import Inbox, OverflowPolicy
from asyncio_actors.supervision import SupervisionStrategy, RestartPolicy

M = TypeVar('M')
R = TypeVar('R')


class ActorRef(Generic[M]):
    """Typed handle to a running actor for message passing."""

    def __init__(self, actor: Actor[M], inbox: Inbox[Any]) -> None: ...

    async def send(self, message: M) -> None: ...

    async def ask(self, message: M, timeout: float = 5.0) -> Any: ...

    @property
    def is_alive(self) -> bool: ...


class Actor(Generic[M]):
    """Base actor class. Subclass and implement on_message()."""

    inbox_size: int
    overflow_policy: OverflowPolicy
    restart_policy: RestartPolicy

    def __init__(self) -> None: ...

    async def on_start(self) -> None: ...

    async def on_message(self, message: M) -> Any: ...

    async def on_stop(self) -> None: ...

    async def on_error(self, error: Exception) -> SupervisionStrategy: ...

    async def reply(self, response: Any) -> None: ...

    async def stop(self) -> None: ...

    def ref(self) -> ActorRef[M]: ...
