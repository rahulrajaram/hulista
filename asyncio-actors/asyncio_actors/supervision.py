"""Supervision strategies for actor lifecycle management."""
from __future__ import annotations

from enum import Enum


class SupervisionStrategy(Enum):
    RESTART = "restart"      # Restart the failed actor
    STOP = "stop"            # Stop the actor permanently
    ESCALATE = "escalate"    # Propagate error to parent supervisor


class RestartPolicy:
    """Configure restart behavior with a sliding window rate limit."""
    __slots__ = ('max_restarts', 'restart_window_seconds', '_restart_times')

    def __init__(self, max_restarts: int = 3, restart_window_seconds: float = 60.0):
        self.max_restarts = max_restarts
        self.restart_window_seconds = restart_window_seconds
        self._restart_times: list[float] = []

    def should_restart(self, current_time: float) -> bool:
        """Return True and record the restart if within the allowed rate.

        Evicts restart records older than ``restart_window_seconds`` before
        checking the count, so the limit is a sliding-window rate limit rather
        than a lifetime cap.
        """
        cutoff = current_time - self.restart_window_seconds
        self._restart_times = [t for t in self._restart_times if t > cutoff]
        if len(self._restart_times) >= self.max_restarts:
            return False
        self._restart_times.append(current_time)
        return True

    def reset(self) -> None:
        """Clear all recorded restart timestamps."""
        self._restart_times.clear()
