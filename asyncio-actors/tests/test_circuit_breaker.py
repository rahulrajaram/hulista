"""Tests for CircuitBreaker."""
from __future__ import annotations

import pytest

from asyncio_actors.circuit_breaker import CircuitBreaker, CircuitState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_breaker(
    failure_threshold: int = 3,
    recovery_timeout: float = 30.0,
    half_open_max_calls: int = 1,
) -> CircuitBreaker:
    return CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        half_open_max_calls=half_open_max_calls,
    )


# We use a monotonic-time injection pattern so tests are not time-dependent.
BASE_TIME = 1_000_000.0


def t(offset: float = 0.0) -> float:
    """Return a synthetic monotonic timestamp."""
    return BASE_TIME + offset


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_starts_closed(self):
        cb = make_breaker()
        assert cb._state == CircuitState.CLOSED

    def test_state_property_returns_closed(self):
        cb = make_breaker()
        assert cb.state == CircuitState.CLOSED

    def test_allow_request_when_closed(self):
        cb = make_breaker()
        assert cb.allow_request(now=t()) is True

    def test_failure_count_zero_initially(self):
        cb = make_breaker()
        assert cb._failure_count == 0


# ---------------------------------------------------------------------------
# Stays CLOSED below failure threshold
# ---------------------------------------------------------------------------

class TestClosedBelowThreshold:
    def test_one_failure_stays_closed(self):
        cb = make_breaker(failure_threshold=3)
        cb.record_failure(now=t())
        assert cb.state == CircuitState.CLOSED

    def test_threshold_minus_one_failures_stays_closed(self):
        cb = make_breaker(failure_threshold=5)
        for i in range(4):
            cb.record_failure(now=t(i))
        assert cb.state == CircuitState.CLOSED

    def test_allow_request_still_true_below_threshold(self):
        cb = make_breaker(failure_threshold=3)
        cb.record_failure(now=t())
        cb.record_failure(now=t(1))
        assert cb.allow_request(now=t(2)) is True

    def test_success_resets_failure_count_in_closed(self):
        cb = make_breaker(failure_threshold=3)
        cb.record_failure(now=t())
        cb.record_failure(now=t(1))
        cb.record_success()
        assert cb._failure_count == 0

    def test_allow_request_after_success_in_closed(self):
        cb = make_breaker(failure_threshold=3)
        cb.record_failure(now=t())
        cb.record_success()
        assert cb.allow_request(now=t(1)) is True


# ---------------------------------------------------------------------------
# Transitions to OPEN after reaching threshold
# ---------------------------------------------------------------------------

class TestTransitionToOpen:
    def test_reaches_threshold_opens_circuit(self):
        cb = make_breaker(failure_threshold=3)
        for i in range(3):
            cb.record_failure(now=t(i))
        assert cb.state == CircuitState.OPEN

    def test_allow_request_false_when_open(self):
        cb = make_breaker(failure_threshold=2)
        cb.record_failure(now=t(0))
        cb.record_failure(now=t(1))
        assert cb.allow_request(now=t(2)) is False

    def test_threshold_one_opens_on_first_failure(self):
        cb = make_breaker(failure_threshold=1)
        cb.record_failure(now=t())
        assert cb.state == CircuitState.OPEN

    def test_extra_failures_beyond_threshold_stay_open(self):
        cb = make_breaker(failure_threshold=2)
        for i in range(5):
            cb.record_failure(now=t(i))
        assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# Rejects requests when OPEN (before timeout)
# ---------------------------------------------------------------------------

class TestRejectsWhenOpen:
    def test_allow_request_false_just_before_timeout(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=30.0)
        cb.record_failure(now=t(0))
        assert cb.allow_request(now=t(29.9)) is False

    def test_allow_request_false_at_zero_elapsed(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=10.0)
        cb.record_failure(now=t(0))
        assert cb.allow_request(now=t(0)) is False

    def test_multiple_rejected_requests(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=60.0)
        cb.record_failure(now=t(0))
        for i in range(10):
            assert cb.allow_request(now=t(i)) is False


# ---------------------------------------------------------------------------
# Transitions to HALF_OPEN after recovery timeout
# ---------------------------------------------------------------------------

class TestTransitionToHalfOpen:
    def test_allow_request_after_timeout_transitions_to_half_open(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=30.0)
        cb.record_failure(now=t(0))
        # Exactly at timeout boundary
        assert cb.allow_request(now=t(30.0)) is True
        assert cb._state == CircuitState.HALF_OPEN

    def test_state_property_reads_half_open_after_timeout(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=10.0)
        cb.record_failure(now=t(0))
        # Check state property (uses time.monotonic internally) — force via allow_request
        cb.allow_request(now=t(11.0))
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_limited_probes(self):
        # When transitioning OPEN -> HALF_OPEN, allow_request returns True but
        # _half_open_calls is reset to 0 (not yet incremented).  The HALF_OPEN
        # quota is consumed by the *next* call that takes the HALF_OPEN branch.
        cb = make_breaker(failure_threshold=1, recovery_timeout=10.0, half_open_max_calls=1)
        cb.record_failure(now=t(0))
        # Transition call: OPEN -> HALF_OPEN, resets _half_open_calls=0, returns True
        assert cb.allow_request(now=t(10.0)) is True
        assert cb._state == CircuitState.HALF_OPEN
        # First probe in HALF_OPEN: _half_open_calls 0 < 1, incremented to 1, allowed
        assert cb.allow_request(now=t(10.01)) is True
        # Quota exhausted: _half_open_calls 1 < 1 is False — rejected
        assert cb.allow_request(now=t(10.02)) is False

    def test_after_timeout_exactly_one_probe_allowed(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=5.0, half_open_max_calls=1)
        cb.record_failure(now=t(0))
        # Transition: OPEN -> HALF_OPEN; _half_open_calls reset to 0
        cb.allow_request(now=t(5.0))
        assert cb._state == CircuitState.HALF_OPEN
        # One probe allowed (consumes the quota)
        assert cb.allow_request(now=t(5.01)) is True
        # No more probes
        assert cb.allow_request(now=t(5.02)) is False


# ---------------------------------------------------------------------------
# HALF_OPEN -> CLOSED on success
# ---------------------------------------------------------------------------

class TestHalfOpenToClosedOnSuccess:
    def test_success_in_half_open_transitions_to_closed(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=10.0)
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(10.0))   # -> HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_closed_after_recovery_allows_requests(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=10.0)
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(10.0))   # -> HALF_OPEN
        cb.record_success()             # -> CLOSED
        assert cb.allow_request(now=t(10.1)) is True

    def test_failure_count_reset_after_recovery(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=10.0)
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(10.0))
        cb.record_success()
        assert cb._failure_count == 0

    def test_multi_probe_half_open_closes_after_all_succeed(self):
        cb = make_breaker(
            failure_threshold=1, recovery_timeout=5.0, half_open_max_calls=2
        )
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(5.0))   # -> HALF_OPEN, probe 1
        cb.record_success()            # success count: 1 (need 2)
        # Should still be HALF_OPEN (not enough successes yet)
        assert cb._state == CircuitState.HALF_OPEN
        cb.allow_request(now=t(5.1))   # probe 2
        cb.record_success()            # success count: 2, -> CLOSED
        assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# HALF_OPEN -> OPEN on failure
# ---------------------------------------------------------------------------

class TestHalfOpenToOpenOnFailure:
    def test_failure_in_half_open_returns_to_open(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=10.0)
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(10.0))   # -> HALF_OPEN
        cb.record_failure(now=t(10.1))  # -> OPEN again
        assert cb._state == CircuitState.OPEN

    def test_requests_rejected_after_half_open_failure(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=10.0)
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(10.0))   # -> HALF_OPEN
        cb.record_failure(now=t(10.1))  # -> OPEN
        assert cb.allow_request(now=t(10.2)) is False

    def test_can_recover_after_second_open(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=5.0)
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(5.0))    # -> HALF_OPEN (first recovery attempt)
        cb.record_failure(now=t(5.1))   # -> OPEN again
        # After another full timeout, should be able to try again
        assert cb.allow_request(now=t(10.2)) is True
        assert cb._state == CircuitState.HALF_OPEN


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_from_closed_stays_closed(self):
        cb = make_breaker()
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_reset_from_open_returns_to_closed(self):
        cb = make_breaker(failure_threshold=1)
        cb.record_failure(now=t(0))
        assert cb._state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_reset_clears_failure_count(self):
        cb = make_breaker(failure_threshold=5)
        for i in range(3):
            cb.record_failure(now=t(i))
        cb.reset()
        assert cb._failure_count == 0

    def test_reset_clears_success_count(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=5.0, half_open_max_calls=2)
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(5.0))
        cb.record_success()
        cb.reset()
        assert cb._success_count == 0

    def test_reset_clears_half_open_calls(self):
        cb = make_breaker(failure_threshold=1, recovery_timeout=5.0, half_open_max_calls=3)
        cb.record_failure(now=t(0))
        cb.allow_request(now=t(5.0))   # -> HALF_OPEN, uses probe slot
        cb.reset()
        assert cb._half_open_calls == 0

    def test_allow_request_true_after_reset(self):
        cb = make_breaker(failure_threshold=1)
        cb.record_failure(now=t(0))
        cb.reset()
        assert cb.allow_request(now=t(1)) is True

    def test_failure_threshold_still_applies_after_reset(self):
        """After reset, the breaker behaves as if freshly constructed."""
        cb = make_breaker(failure_threshold=2)
        # First open cycle
        cb.record_failure(now=t(0))
        cb.record_failure(now=t(1))
        assert cb._state == CircuitState.OPEN
        cb.reset()
        # Single failure should NOT open the circuit again
        cb.record_failure(now=t(2))
        assert cb.state == CircuitState.CLOSED
        # Second failure hits the threshold
        cb.record_failure(now=t(3))
        assert cb.state == CircuitState.OPEN
