"""Predicate dispatch — dispatch on runtime values, not just types."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def predicate(condition: Callable[..., bool]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to add a predicate condition to a dispatch handler.

    Usage:
        @dispatch.register
        @predicate(lambda task: task.priority > 8)
        def handle_urgent(task: Task) -> Result:
            return fast_track(task)
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, "__dispatch_predicate__", condition)
        return func
    return decorator
