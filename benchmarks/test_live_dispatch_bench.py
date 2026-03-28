from __future__ import annotations

from live_dispatch import Dispatcher


def test_live_dispatch_cached_call(benchmark) -> None:
    dispatch = Dispatcher("bench")

    @dispatch.register
    def handle_int(value: int) -> int:
        return value + 1

    assert dispatch(1) == 2
    result = benchmark(lambda: dispatch(41))
    assert result == 42

