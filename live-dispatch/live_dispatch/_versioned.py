"""Versioned dispatch tables with rollback support."""
from __future__ import annotations

from typing import Any
from contextlib import contextmanager


class VersionedContext:
    """Context manager for versioned handler registration with rollback."""

    def __init__(self, dispatcher):
        self._dispatcher = dispatcher
        self._snapshot = None

    def __enter__(self):
        # Save current handler state
        self._snapshot = list(self._dispatcher._handlers)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Don't auto-rollback — user must explicitly call rollback()
        return False

    def rollback(self):
        """Restore handlers to the state before this context was entered."""
        if self._snapshot is not None:
            self._dispatcher._handlers = list(self._snapshot)
            self._dispatcher._cache.clear()
            self._dispatcher._has_predicates = any(
                h.predicate is not None for h in self._dispatcher._handlers
            )


def versioned(dispatcher):
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
