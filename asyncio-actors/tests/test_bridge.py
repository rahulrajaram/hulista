"""Tests for PersistentBridge — async-sync bridge."""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import pytest

from asyncio_actors.bridge import PersistentBridge


@pytest.fixture
def bridge_and_loop():
    """Create an event loop running in a background thread with a bridge."""
    loop = asyncio.new_event_loop()
    bridge = PersistentBridge(loop)
    ready = threading.Event()

    def run_loop():
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    assert ready.wait(timeout=1.0)
    yield bridge, loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.close()


# ---------------------------------------------------------------------------
# call() — fire and forget
# ---------------------------------------------------------------------------

def test_call_fire_and_forget(bridge_and_loop):
    bridge, loop = bridge_and_loop
    results = []

    async def append_value(val):
        results.append(val)

    bridge.call(append_value, 42)
    # Give the loop time to process
    import time
    time.sleep(0.1)
    assert results == [42]


def test_call_multiple(bridge_and_loop):
    bridge, loop = bridge_and_loop
    results = []

    async def append_value(val):
        results.append(val)

    for i in range(5):
        bridge.call(append_value, i)

    import time
    time.sleep(0.2)
    assert sorted(results) == [0, 1, 2, 3, 4]


def test_call_logs_exceptions(bridge_and_loop, caplog):
    bridge, loop = bridge_and_loop

    async def boom():
        raise ValueError("fire and forget exploded")

    with caplog.at_level(logging.ERROR):
        bridge.call(boom)
        # Deterministic sync: noop runs after boom's done-callback fires
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0), loop).result(timeout=1.0)

    assert "PersistentBridge.call() task failed" in caplog.text


# ---------------------------------------------------------------------------
# call_wait() — blocking wait for result
# ---------------------------------------------------------------------------

def test_call_wait_returns_result(bridge_and_loop):
    bridge, loop = bridge_and_loop

    async def double(x):
        return x * 2

    result = bridge.call_wait(double, 21)
    assert result == 42


def test_call_wait_with_string(bridge_and_loop):
    bridge, loop = bridge_and_loop

    async def greet(name):
        return f"hello, {name}"

    result = bridge.call_wait(greet, "world")
    assert result == "hello, world"


def test_call_wait_async_sleep(bridge_and_loop):
    bridge, loop = bridge_and_loop

    async def slow_add(a, b):
        await asyncio.sleep(0.05)
        return a + b

    result = bridge.call_wait(slow_add, 3, 4)
    assert result == 7


# ---------------------------------------------------------------------------
# call_wait() with timeout
# ---------------------------------------------------------------------------

def test_call_wait_timeout_succeeds(bridge_and_loop):
    bridge, loop = bridge_and_loop

    async def fast():
        return "done"

    result = bridge.call_wait(fast, timeout=5.0)
    assert result == "done"


def test_call_wait_timeout_expires(bridge_and_loop):
    bridge, loop = bridge_and_loop

    async def very_slow():
        await asyncio.sleep(100)
        return "never"

    with pytest.raises(concurrent.futures.TimeoutError):
        bridge.call_wait(very_slow, timeout=0.05)


# ---------------------------------------------------------------------------
# Exception propagation
# ---------------------------------------------------------------------------

def test_call_wait_exception_propagated(bridge_and_loop):
    bridge, loop = bridge_and_loop

    async def boom():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        bridge.call_wait(boom)


def test_call_wait_runtime_error_propagated(bridge_and_loop):
    bridge, loop = bridge_and_loop

    async def fail():
        raise RuntimeError("runtime failure")

    with pytest.raises(RuntimeError, match="runtime failure"):
        bridge.call_wait(fail)


def test_call_wait_type_error_propagated(bridge_and_loop):
    bridge, loop = bridge_and_loop

    async def bad_types():
        return 1 + "string"

    with pytest.raises(TypeError):
        bridge.call_wait(bad_types)
