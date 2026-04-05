"""Runtime-extensible dispatch system with multiple dispatch support."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, cast, get_type_hints

_Args = tuple[Any, ...]
_Kwargs = dict[str, Any]
_TypeSpec = dict[str, type[Any]]
_HandlerFunc = Callable[..., Any]


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
        self._fallback: _HandlerFunc | None = None
        self._cache: dict[tuple[type[Any], ...], _Handler | None] = {}
        self._has_predicates = False

    def register(
        self,
        func: _HandlerFunc | None = None,
        *,
        priority: int = 0,
    ) -> Callable[[_HandlerFunc], _HandlerFunc] | _HandlerFunc:
        """Register a handler function. Can be used as decorator or called directly.

        Dispatch is based on type annotations of the function's parameters.
        """
        def decorator(fn: _HandlerFunc) -> _HandlerFunc:
            try:
                sig = inspect.signature(fn)
            except (ValueError, TypeError):
                sig = None

            type_spec: _TypeSpec = {}
            if sig is None:
                # Can't introspect — register with empty type_spec
                pred = getattr(fn, '__dispatch_predicate__', None)
                if pred is not None:
                    self._has_predicates = True
                handler = _Handler(
                    fn,
                    signature=None,
                    type_spec=type_spec,
                    priority=priority,
                    predicate=pred,
                )
                self._handlers.append(handler)
                self._handlers.sort(key=lambda h: -h.priority)
                self._cache.clear()
                return fn

            try:
                hints = get_type_hints(fn)
            except (AttributeError, NameError, TypeError) as exc:
                raise TypeError(
                    f"Dispatcher '{self._name}' could not resolve runtime annotations "
                    f"for handler '{fn.__qualname__}': {exc}"
                ) from exc

            dispatchable_params = [
                param for param in sig.parameters.values()
                if param.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                )
            ]
            has_runtime_annotations = any(param.name in hints for param in dispatchable_params)
            if has_runtime_annotations:
                required_untyped = [
                    param.name
                    for param in dispatchable_params
                    if param.name not in hints and param.default is inspect.Parameter.empty
                ]
                if required_untyped:
                    names = ", ".join(required_untyped)
                    raise TypeError(
                        f"Dispatcher '{self._name}' requires all required parameters to "
                        f"have plain runtime type annotations once a handler uses "
                        f"dispatch annotations. Untyped required parameter(s): {names}"
                    )

            for param in sig.parameters.values():
                if param.name not in hints:
                    continue
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    raise TypeError(
                        f"Dispatcher '{self._name}' does not support annotated "
                        f"variadic parameters on handler '{fn.__qualname__}'"
                    )
                type_spec[param.name] = _normalize_runtime_annotation(
                    hints[param.name],
                    dispatcher_name=self._name,
                    func=fn,
                    param_name=param.name,
                )

            pred = getattr(fn, '__dispatch_predicate__', None)
            if pred is not None:
                self._has_predicates = True
            handler = _Handler(
                fn,
                signature=sig,
                type_spec=type_spec,
                priority=priority,
                predicate=pred,
            )
            self._handlers.append(handler)
            self._handlers.sort(key=lambda h: -h.priority)
            self._cache.clear()
            return fn

        if func is not None:
            return decorator(func)
        return decorator

    def fallback(self, func: _HandlerFunc) -> _HandlerFunc:
        """Register a fallback handler for when no type match is found."""
        self._fallback = func
        return func

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
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

    def unregister(self, func: _HandlerFunc) -> None:
        """Remove a handler by function reference."""
        self._handlers = [h for h in self._handlers if h.func is not func]
        self._refresh_predicate_state()
        self._cache.clear()

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
        self._fallback = None
        self._refresh_predicate_state()
        self._cache.clear()

    def _refresh_predicate_state(self) -> None:
        self._has_predicates = any(h.predicate is not None for h in self._handlers)

    def _find_handler(self, args: _Args, kwargs: _Kwargs) -> _Handler | None:
        """Find the best matching handler, using cache when possible."""
        if not kwargs and not self._has_predicates:
            key = tuple(type(a) for a in args)
            cached = self._cache.get(key, _SENTINEL)
            if cached is not _SENTINEL:
                return cast(_Handler | None, cached)

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

    async def call_async(self, *args: Any, **kwargs: Any) -> Any:
        """Async dispatch — calls the handler and awaits if it returns a coroutine."""
        handler = self._find_handler(args, kwargs)
        if handler is not None:
            result = handler.func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        if self._fallback is not None:
            result = self._fallback(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        raise TypeError(
            f"No handler in dispatcher '{self._name}' matches "
            f"arguments: {_format_args(args, kwargs)}"
        )

    def verify_exhaustive(self, sealed_base: type[Any]) -> None:
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
    __slots__ = ('func', 'signature', 'type_spec', 'priority', 'predicate')

    def __init__(
        self,
        func: _HandlerFunc,
        signature: inspect.Signature | None,
        type_spec: _TypeSpec,
        priority: int = 0,
        predicate: _HandlerFunc | None = None,
    ) -> None:
        self.func = func
        self.signature = signature
        self.type_spec = type_spec  # {param_name: type}
        self.priority = priority
        self.predicate = predicate

    def matches(self, args: _Args, kwargs: _Kwargs) -> bool:
        if self.predicate is not None:
            try:
                if not self.predicate(*args, **kwargs):
                    return False
            except (TypeError, Exception):
                return False

        if self.signature is None:
            return True

        try:
            bound = self.signature.bind(*args, **kwargs)
        except TypeError:
            return False
        bound.apply_defaults()

        if not self.type_spec:
            return True

        for param_name, expected_type in self.type_spec.items():
            val = bound.arguments[param_name]
            if not isinstance(val, expected_type):
                return False

        return True


def _format_args(args: _Args, kwargs: _Kwargs) -> str:
    parts = [repr(a) for a in args]
    parts += [f"{k}={v!r}" for k, v in kwargs.items()]
    return ', '.join(parts)


def _normalize_runtime_annotation(
    annotation: Any,
    *,
    dispatcher_name: str,
    func: Callable,
    param_name: str,
) -> type:
    if annotation is Any:
        raise TypeError(
            f"Dispatcher '{dispatcher_name}' does not support typing.Any for "
            f"parameter '{param_name}' on handler '{func.__qualname__}'"
        )
    if isinstance(annotation, type):
        return annotation
    raise TypeError(
        f"Dispatcher '{dispatcher_name}' only supports plain runtime classes for "
        f"parameter '{param_name}' on handler '{func.__qualname__}', got {annotation!r}"
    )
