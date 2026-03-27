"""Tests for asyncio_actors.supervision."""
from __future__ import annotations

import pytest

from asyncio_actors.supervision import RestartPolicy, SupervisionStrategy


# ---------------------------------------------------------------------------
# SupervisionStrategy enum
# ---------------------------------------------------------------------------

def test_strategy_values():
    assert SupervisionStrategy.RESTART.value == "restart"
    assert SupervisionStrategy.STOP.value == "stop"
    assert SupervisionStrategy.ESCALATE.value == "escalate"


# ---------------------------------------------------------------------------
# RestartPolicy — basic should_restart
# ---------------------------------------------------------------------------

def test_should_restart_allows_within_limit():
    policy = RestartPolicy(max_restarts=3, restart_window_seconds=60.0)
    t = 1000.0
    assert policy.should_restart(t) is True
    assert policy.should_restart(t + 1) is True
    assert policy.should_restart(t + 2) is True


def test_should_restart_blocks_after_limit():
    policy = RestartPolicy(max_restarts=2, restart_window_seconds=60.0)
    t = 1000.0
    policy.should_restart(t)
    policy.should_restart(t + 1)
    # Third call in the same window must be rejected.
    assert policy.should_restart(t + 2) is False


def test_should_restart_sliding_window_evicts_old_entries():
    policy = RestartPolicy(max_restarts=2, restart_window_seconds=10.0)
    t0 = 1000.0
    # Use up both slots.
    policy.should_restart(t0)
    policy.should_restart(t0 + 1)
    # Advance time past the window so both entries expire.
    t1 = t0 + 11.0
    # Both old entries are outside the window → should restart again.
    assert policy.should_restart(t1) is True


def test_restart_count_is_rolling_not_lifetime():
    """With a 10-second window and limit=2, restarts are allowed in new windows."""
    policy = RestartPolicy(max_restarts=2, restart_window_seconds=10.0)
    t = 500.0
    assert policy.should_restart(t) is True        # 1st in window
    assert policy.should_restart(t + 5) is True    # 2nd in window
    assert policy.should_restart(t + 6) is False   # 3rd in same window — rejected

    # New window: both old entries expired.
    assert policy.should_restart(t + 20) is True   # 1st in new window
    assert policy.should_restart(t + 21) is True   # 2nd in new window
    assert policy.should_restart(t + 22) is False  # 3rd in new window — rejected


# ---------------------------------------------------------------------------
# RestartPolicy — reset
# ---------------------------------------------------------------------------

def test_reset_clears_history():
    policy = RestartPolicy(max_restarts=2, restart_window_seconds=60.0)
    t = 1000.0
    policy.should_restart(t)
    policy.should_restart(t + 1)
    # Limit reached.
    assert policy.should_restart(t + 2) is False
    # After reset the count is cleared.
    policy.reset()
    assert policy.should_restart(t + 2) is True


def test_reset_is_idempotent():
    policy = RestartPolicy(max_restarts=3, restart_window_seconds=60.0)
    policy.reset()
    policy.reset()
    assert policy.should_restart(0.0) is True


# ---------------------------------------------------------------------------
# RestartPolicy — edge cases
# ---------------------------------------------------------------------------

def test_zero_max_restarts_never_allows():
    policy = RestartPolicy(max_restarts=0, restart_window_seconds=60.0)
    assert policy.should_restart(0.0) is False


def test_large_window_keeps_all_entries():
    policy = RestartPolicy(max_restarts=5, restart_window_seconds=3600.0)
    for i in range(5):
        assert policy.should_restart(float(i)) is True
    assert policy.should_restart(5.0) is False


def test_policy_is_independent_across_instances():
    p1 = RestartPolicy(max_restarts=1, restart_window_seconds=60.0)
    p2 = RestartPolicy(max_restarts=1, restart_window_seconds=60.0)
    p1.should_restart(0.0)
    assert p1.should_restart(1.0) is False
    # p2 has not been used, so it should still allow a restart.
    assert p2.should_restart(0.0) is True
