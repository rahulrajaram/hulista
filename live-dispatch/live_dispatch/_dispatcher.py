"""Runtime-extensible dispatch system with multiple dispatch support."""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, get_type_hints


class Dispatcher:
    """Runtime-extensible function dispatcher.

    Supports:
    - Single dispatch on first argument type
    - Multiple dispatch on multiple argument types
    - Runtime handler registration (agents can add handlers dynamically)
    - Handler listing and introspection

    Usage:
        dispatch = Dispatcher("process")

        @dispatch.register
        def process_int(x: int) -> str:
            return f"integer: {x}"

        @dispatch.register
        def process_str(x: str) -> str:
            return f"string: {x}"

        dispatch(42)     # "integer: 42"
        dispatch("hi")   # "string: hi"
    """

    def __init__(self, name: str = "dispatcher"):
        self._name = name
        self._handlers: list[_Handler] = []
        self._fallback: Callable | None = None

    def register(self, func: Callable | None = None, *, priority: int = 0) -> Callable:
        """Register a handler function. Can be used as decorator or called directly.

        Dispatch is based on type annotations of the function's parameters.
        """
        def decorator(fn: Callable) -> Callable:
            hints = {}
            try:
                sig = inspect.signature(fn)
                hints = get_type_hints(fn)
            except (ValueError, TypeError):
                pass

            type_spec = {}
            for param_name, param in sig.parameters.items():
                if param_name in hints and hints[param_name] is not inspect.Parameter.empty:
                    ann = hints[param_name]
                    if isinstance(ann, type):
                        type_spec[param_name] = ann

            pred = getattr(fn, '__dispatch_predicate__', None)
            handler = _Handler(fn, type_spec, priority=priority, predicate=pred)
            self._handlers.append(handler)
            self._handlers.sort(key=lambda h: -h.priority)
            return fn

        if func is not None:
            return decorator(func)
        return decorator

    def fallback(self, func: Callable) -> Callable:
        """Register a fallback handler for when no type match is found."""
        self._fallback = func
        return func

    def __call__(self, *args, **kwargs) -> Any:
        """Dispatch to the best matching handler."""
        for handler in self._handlers:
            if handler.matches(args, kwargs):
                return handler.func(*args, **kwargs)

        if self._fallback is not None:
            return self._fallback(*args, **kwargs)

        raise TypeError(
            f"No handler in dispatcher '{self._name}' matches "
            f"arguments: {_format_args(args, kwargs)}"
        )

    def handlers(self) -> list[dict[str, Any]]:
        """Introspect registered handlers."""
        return [
            {
                "function": h.func.__qualname__,
                "types": {k: v.__name__ for k, v in h.type_spec.items()},
                "priority": h.priority,
                "predicate": h.predicate is not None,
            }
            for h in self._handlers
        ]

    def unregister(self, func: Callable) -> None:
        """Remove a handler by function reference."""
        self._handlers = [h for h in self._handlers if h.func is not func]

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        self._fallback = None

    def __repr__(self) -> str:
        return f"Dispatcher('{self._name}', handlers={len(self._handlers)})"


class _Handler:
    __slots__ = ('func', 'type_spec', 'priority', 'predicate')

    def __init__(self, func, type_spec, priority=0, predicate=None):
        self.func = func
        self.type_spec = type_spec  # {param_name: type}
        self.priority = priority
        self.predicate = predicate

    def matches(self, args, kwargs) -> bool:
        if self.predicate is not None:
            try:
                if not self.predicate(*args, **kwargs):
                    return False
            except (TypeError, Exception):
                return False

        if not self.type_spec:
            return True

        sig = inspect.signature(self.func)
        params = list(sig.parameters.keys())

        for i, (param_name, expected_type) in enumerate(self.type_spec.items()):
            if param_name in kwargs:
                val = kwargs[param_name]
            elif i < len(args):
                val = args[i]
            else:
                return False
            if not isinstance(val, expected_type):
                return False

        return True


def _format_args(args, kwargs):
    parts = [repr(a) for a in args]
    parts += [f"{k}={v!r}" for k, v in kwargs.items()]
    return ', '.join(parts)
