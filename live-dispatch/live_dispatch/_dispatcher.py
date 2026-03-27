"""Runtime-extensible dispatch system with multiple dispatch support."""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, get_type_hints


class Dispatcher:
    """Runtime-extensible function dispatcher.

    Supports:
    - Single dispatch on first argument type
    - Multiple dispatch on multiple argument types
    - Runtime handler registration (agents can add handlers dynamically)
    - Handler listing and introspection
    - O(1) amortized dispatch via type-signature cache

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
        self._cache: dict[tuple[type, ...], _Handler | None] = {}
        self._has_predicates = False

    def register(self, func: Callable | None = None, *, priority: int = 0) -> Callable:
        """Register a handler function. Can be used as decorator or called directly.

        Dispatch is based on type annotations of the function's parameters.
        """
        def decorator(fn: Callable) -> Callable:
            hints = {}
            sig = None
            try:
                sig = inspect.signature(fn)
                hints = get_type_hints(fn)
            except (ValueError, TypeError):
                pass

            type_spec = {}
            if sig is None:
                # Can't introspect — register with empty type_spec
                pred = getattr(fn, '__dispatch_predicate__', None)
                if pred is not None:
                    self._has_predicates = True
                handler = _Handler(fn, type_spec, priority=priority, predicate=pred)
                self._handlers.append(handler)
                self._handlers.sort(key=lambda h: -h.priority)
                self._cache.clear()
                return fn

            for param_name, _ in sig.parameters.items():
                if param_name in hints and hints[param_name] is not inspect.Parameter.empty:
                    ann = hints[param_name]
                    if isinstance(ann, type):
                        type_spec[param_name] = ann

            pred = getattr(fn, '__dispatch_predicate__', None)
            if pred is not None:
                self._has_predicates = True
            handler = _Handler(fn, type_spec, priority=priority, predicate=pred)
            self._handlers.append(handler)
            self._handlers.sort(key=lambda h: -h.priority)
            self._cache.clear()
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
        handler = self._find_handler(args, kwargs)
        if handler is not None:
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
        self._cache.clear()

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        self._fallback = None
        self._cache.clear()

    def _find_handler(self, args, kwargs) -> _Handler | None:
        """Find the best matching handler, using cache when possible."""
        if not kwargs and not self._has_predicates:
            key = tuple(type(a) for a in args)
            cached = self._cache.get(key, _SENTINEL)
            if cached is not _SENTINEL:
                return cached

            for handler in self._handlers:
                if handler.matches(args, kwargs):
                    self._cache[key] = handler
                    return handler
            self._cache[key] = None
            return None

        for handler in self._handlers:
            if handler.matches(args, kwargs):
                return handler
        return None

    async def call_async(self, *args, **kwargs) -> Any:
        """Async dispatch — calls the handler and awaits if it returns a coroutine."""
        handler = self._find_handler(args, kwargs)
        if handler is not None:
            result = handler.func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result

        if self._fallback is not None:
            result = self._fallback(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result

        raise TypeError(
            f"No handler in dispatcher '{self._name}' matches "
            f"arguments: {_format_args(args, kwargs)}"
        )

    def verify_exhaustive(self, sealed_base: type) -> None:
        """Assert that registered handlers cover all sealed subclasses.

        Args:
            sealed_base: A class decorated with @sealed from sealed_typing.

        Raises:
            TypeError: If the sealed base has subclasses not covered by handlers,
                       or if sealed_base is not a sealed class.
        """
        if not getattr(sealed_base, '__sealed__', False):
            raise TypeError(f"'{sealed_base.__qualname__}' is not a sealed class")

        sealed_subs = frozenset(getattr(sealed_base, '__sealed_subclasses__', set()))
        covered_types = set()
        for h in self._handlers:
            for typ in h.type_spec.values():
                if isinstance(typ, type):
                    covered_types.add(typ)

        missing = sealed_subs - covered_types
        if missing:
            missing_names = ', '.join(sorted(c.__qualname__ for c in missing))
            raise TypeError(
                f"Dispatcher '{self._name}' does not cover all subclasses of "
                f"sealed class '{sealed_base.__qualname__}'. "
                f"Missing: {missing_names}"
            )

    def __repr__(self) -> str:
        return f"Dispatcher('{self._name}', handlers={len(self._handlers)})"


_SENTINEL = object()


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
