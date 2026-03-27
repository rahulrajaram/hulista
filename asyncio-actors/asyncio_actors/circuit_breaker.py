"""Circuit breaker pattern for failure management.

States:
    CLOSED  — normal operation, requests pass through
    OPEN    — too many failures, requests are rejected immediately
    HALF_OPEN — testing recovery, one request allowed through
"""
from __future__ import annotations

import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit is open and not allowing requests."""
    pass


class CircuitBreaker:
    """Circuit breaker with CLOSED/OPEN/HALF_OPEN state machine.

    Usage::

        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

        if breaker.allow_request():
            try:
                result = do_work()
                breaker.record_success()
            except Exception:
                breaker.record_failure()
    """

    __slots__ = (
        '_failure_threshold', '_recovery_timeout', '_half_open_max_calls',
        '_state', '_failure_count', '_success_count',
        '_last_failure_time', '_half_open_calls',
    )

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """Current circuit state, evaluating timeouts."""
        if self._state == CircuitState.OPEN:
            now = time.monotonic()
            if now - self._last_failure_time >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def allow_request(self, now: float | None = None) -> bool:
        """Check if a request should be allowed through.

        Args:
            now: Current monotonic time (for testing). Uses time.monotonic() if None.
        """
        if now is None:
            now = time.monotonic()

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            if now - self._last_failure_time >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                return True
            return False

        # HALF_OPEN
        if self._half_open_calls < self._half_open_max_calls:
            self._half_open_calls += 1
            return True
        return False

    def record_failure(self, now: float | None = None) -> None:
        """Record a failed request.

        Args:
            now: Current monotonic time (for testing). Uses time.monotonic() if None.
        """
        if now is None:
            now = time.monotonic()

        self._last_failure_time = now

        if self._state == CircuitState.HALF_OPEN:
            # Failure during recovery — go back to OPEN
            self._state = CircuitState.OPEN
            return

        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful request."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._half_open_max_calls:
                self.reset()
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def reset(self) -> None:
        """Reset the circuit breaker to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
