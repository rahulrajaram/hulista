"""Predicate dispatch — dispatch on runtime values, not just types."""
from __future__ import annotations

from typing import Callable, Any


def predicate(condition: Callable[..., bool]):
    """Decorator to add a predicate condition to a dispatch handler.

    Usage:
        @dispatch.register
        @predicate(lambda task: task.priority > 8)
        def handle_urgent(task: Task) -> Result:
            return fast_track(task)
    """
    def decorator(func: Callable) -> Callable:
        func.__dispatch_predicate__ = condition
        return func
    return decorator
