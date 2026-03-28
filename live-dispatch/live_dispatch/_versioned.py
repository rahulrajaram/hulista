"""Versioned dispatch tables with rollback support."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol, Self


class _SupportsVersionedDispatch(Protocol):
    _handlers: list[Any]
    _fallback: Callable[..., Any] | None
    _cache: dict[tuple[type[Any], ...], Any]
    _has_predicates: bool


class VersionedContext:
    """Context manager for versioned handler registration with rollback."""

    def __init__(self, dispatcher: _SupportsVersionedDispatch) -> None:
        self._dispatcher = dispatcher
        self._snapshot: dict[str, Any] | None = None

    def __enter__(self) -> Self:
        # Save full dispatcher state so rollback is lossless.
        self._snapshot = {
            "handlers": list(self._dispatcher._handlers),
            "fallback": self._dispatcher._fallback,
            "cache": dict(self._dispatcher._cache),
            "has_predicates": self._dispatcher._has_predicates,
        }
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> Literal[False]:
        # Don't auto-rollback — user must explicitly call rollback()
        return False

    def rollback(self) -> None:
        """Restore handlers to the state before this context was entered."""
        if self._snapshot is not None:
            self._dispatcher._handlers = list(self._snapshot["handlers"])
            self._dispatcher._fallback = self._snapshot["fallback"]
            self._dispatcher._cache = dict(self._snapshot["cache"])
            self._dispatcher._has_predicates = self._snapshot["has_predicates"]


def versioned(dispatcher: _SupportsVersionedDispatch) -> VersionedContext:
    """Create a versioned context for a dispatcher.

    Usage:
        with versioned(dispatch) as v:
            dispatch.register(experimental_handler)
            try:
                result = dispatch(task)
            except:
                v.rollback()  # Restores previous handler set
    """
    return VersionedContext(dispatcher)
