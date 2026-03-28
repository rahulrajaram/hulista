from __future__ import annotations

import inspect


from live_dispatch import Dispatcher


def test_register_handles_uninspectable_callables(monkeypatch) -> None:
    dispatch = Dispatcher("internal")

    class CallableObject:
        def __call__(self, value: int) -> int:
            return value + 1

    callable_object = CallableObject()
    monkeypatch.setattr(inspect, "signature", lambda fn: (_ for _ in ()).throw(ValueError("no signature")))

    returned = dispatch.register(callable_object)

    assert returned is callable_object
    assert dispatch(1) == 2

