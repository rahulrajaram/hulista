"""Type stubs for CollectorTaskGroup."""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine, TypeVar

T = TypeVar('T')


class CollectorTaskGroup:
    """An asyncio.TaskGroup that does NOT cancel siblings on first error."""

    def __init__(self) -> None: ...

    async def __aenter__(self) -> CollectorTaskGroup: ...

    async def __aexit__(
        self,
        et: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool | None: ...

    def create_task(
        self, coro: Coroutine[Any, Any, T], **kwargs: Any
    ) -> asyncio.Task[T]: ...

    def __repr__(self) -> str: ...
