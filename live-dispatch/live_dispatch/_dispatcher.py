"""Runtime-extensible dispatch system with multiple dispatch support."""
from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

_Args = tuple[Any, ...]
_Kwargs = dict[str, Any]
# A resolved type spec value is either a plain type or a tuple of types (for Union).
_ResolvedType = type[Any] | tuple[type[Any], ...]
_TypeSpec = dict[str, _ResolvedType]
_HandlerFunc = Callable[..., Any]

# Sentinel for "not in cache yet"
_SENTINEL = object()


class AmbiguousDispatchError(TypeError):
    """Raised by a specificity-mode Dispatcher when two handlers are equidistant.

    This happens when two registered handlers match the argument types and their
    registered types are at the same MRO distance from the actual argument type.
    """


class Dispatcher:
    """Runtime-extensible function dispatcher.

    Supports:
    - Single dispatch on first argument type
    - Multiple dispatch on multiple argument types
    - Runtime handler registration (agents can add handlers dynamically)
    - Handler listing and introspection
    - O(1) amortised dispatch via type-signature cache
    - Union type annotations  (``int | str`` or ``Union[int, str]``)
    - ``@runtime_checkable`` Protocol annotations
    - Specificity-based resolution (opt-in via ``specificity=True``)

    Usage::

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

    def __init__(self, name: str = "dispatcher", *, specificity: bool = False) -> None:
        self._name = name
        self._specificity = specificity
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
        """Register a handler function.  Can be used as decorator or called directly.

        Dispatch is based on type annotations of the function's parameters.
        Supported annotation forms:

        - Plain class: ``x: int``
        - Union: ``x: int | str``  or  ``x: Union[int, str]``
        - ``@runtime_checkable`` Protocol: ``x: MyProto``
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
                "types": {k: _type_spec_repr(v) for k, v in h.type_spec.items()},
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
        if self._specificity:
            return self._find_handler_by_specificity(args, kwargs)

        if not kwargs and not self._has_predicates:
            key = tuple(type(a) for a in args)
            cached = self._cache.get(key, _SENTINEL)
            if cached is not _SENTINEL:
                return cast(_Handler | None, cached)

            result = self._find_first_matching(args, kwargs)
            self._cache[key] = result
            return result

        return self._find_first_matching(args, kwargs)

    def _find_first_matching(self, args: _Args, kwargs: _Kwargs) -> _Handler | None:
        """Return the first handler (by priority order) that matches."""
        for handler in self._handlers:
            if handler.matches(args, kwargs):
                return handler
        return None

    def _find_handler_by_specificity(
        self,
        args: _Args,
        kwargs: _Kwargs,
    ) -> _Handler | None:
        """Return the most-specific matching handler, raising on ambiguity.

        Specificity is measured as the MRO distance from the actual argument
        type to the handler's registered type.  A lower total distance means
        a more-specific handler.  If two handlers are equidistant,
        ``AmbiguousDispatchError`` is raised.
        """
        # Build a list of (handler, total_mro_distance) for every match.
        matching: list[tuple[_Handler, int]] = []

        for handler in self._handlers:
            if not handler.matches(args, kwargs):
                continue

            # Compute the total MRO distance across all typed parameters.
            if handler.signature is None:
                # No inspectable signature — treat as wildcard (distance 0)
                matching.append((handler, 0))
                continue
            try:
                bound = handler.signature.bind(*args, **kwargs)
            except TypeError:
                matching.append((handler, 0))
                continue
            bound.apply_defaults()

            total_dist = 0
            for param_name, registered_type in handler.type_spec.items():
                val = bound.arguments[param_name]
                actual_type = type(val)
                total_dist += _mro_distance(actual_type, registered_type)

            matching.append((handler, total_dist))

        if not matching:
            return None
        if len(matching) == 1:
            return matching[0][0]

        # Sort by ascending distance (most specific first).
        matching.sort(key=lambda t: t[1])
        best_dist = matching[0][1]
        best_handlers = [h for h, d in matching if d == best_dist]

        if len(best_handlers) > 1:
            names = ", ".join(h.func.__qualname__ for h in best_handlers)
            raise AmbiguousDispatchError(
                f"Dispatcher '{self._name}' cannot resolve ambiguous handlers "
                f"with equal MRO distance: {names}"
            )

        return best_handlers[0]

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
        covered_types: set[type[Any]] = set()
        for h in self._handlers:
            for resolved in h.type_spec.values():
                if isinstance(resolved, tuple):
                    for t in resolved:
                        if isinstance(t, type):
                            covered_types.add(t)
                elif isinstance(resolved, type):
                    covered_types.add(resolved)

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
        self.type_spec = type_spec  # {param_name: type or tuple-of-types}
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_args(args: _Args, kwargs: _Kwargs) -> str:
    parts = [repr(a) for a in args]
    parts += [f"{k}={v!r}" for k, v in kwargs.items()]
    return ', '.join(parts)


def _type_spec_repr(resolved: _ResolvedType) -> str:
    """Return a human-readable name for a resolved type spec value."""
    if isinstance(resolved, tuple):
        return "Union[" + ", ".join(t.__name__ for t in resolved) + "]"
    return resolved.__name__


def _is_protocol(annotation: Any) -> bool:
    """Return True if *annotation* is a user-defined typing.Protocol subclass.

    We check the MRO directly because ``issubclass(int, typing.Protocol)`` can
    return ``True`` on some CPython versions, which would incorrectly classify
    built-in types as protocols.
    """
    return (
        isinstance(annotation, type)
        and typing.Protocol in annotation.__mro__
        and annotation is not typing.Protocol
    )


def _normalize_runtime_annotation(
    annotation: Any,
    *,
    dispatcher_name: str,
    func: Callable[..., Any],
    param_name: str,
) -> _ResolvedType:
    """Validate and normalise a parameter annotation for dispatch.

    Accepted forms:
    - ``typing.Any`` — rejected with TypeError
    - Plain class — returned as-is
    - ``@runtime_checkable`` Protocol subclass — returned as-is (isinstance works)
    - Non-runtime-checkable Protocol — rejected with TypeError
    - ``Union[A, B]`` / ``A | B`` — returned as a tuple of member types

    Returns a ``type`` or a ``tuple[type, ...]`` suitable for use with
    ``isinstance()``.
    """
    if annotation is Any:
        raise TypeError(
            f"Dispatcher '{dispatcher_name}' does not support typing.Any for "
            f"parameter '{param_name}' on handler '{func.__qualname__}'"
        )

    # Check for Union: typing.Union or Python 3.10+ types.UnionType (X | Y)
    origin = get_origin(annotation)
    if origin is Union or isinstance(annotation, types.UnionType):
        member_args = get_args(annotation)
        resolved_members: list[type[Any]] = []
        for arg in member_args:
            if arg is type(None):
                # Allow None / NoneType in union
                resolved_members.append(type(None))
                continue
            if not isinstance(arg, type):
                raise TypeError(
                    f"Dispatcher '{dispatcher_name}' Union annotation for "
                    f"parameter '{param_name}' on handler '{func.__qualname__}' "
                    f"contains a non-type member: {arg!r}"
                )
            resolved_members.append(arg)
        if not resolved_members:
            raise TypeError(
                f"Dispatcher '{dispatcher_name}' Union annotation for "
                f"parameter '{param_name}' on handler '{func.__qualname__}' "
                f"is empty"
            )
        return tuple(resolved_members)

    # Check for Protocol — must be @runtime_checkable
    if _is_protocol(annotation):
        if not getattr(annotation, '_is_runtime_protocol', False):
            raise TypeError(
                f"Dispatcher '{dispatcher_name}' requires Protocol types to be "
                f"decorated with @runtime_checkable, but '{annotation.__qualname__}' "
                f"is not. Add @runtime_checkable to '{annotation.__qualname__}'."
            )
        # _is_protocol() confirmed annotation is a type; isinstance() works on
        # runtime_checkable Protocols, so cast is safe here.
        return cast(type[Any], annotation)

    if isinstance(annotation, type):
        return annotation

    raise TypeError(
        f"Dispatcher '{dispatcher_name}' only supports plain runtime classes, "
        f"Union types, or @runtime_checkable Protocols for "
        f"parameter '{param_name}' on handler '{func.__qualname__}', got {annotation!r}"
    )


def _mro_distance(actual: type[Any], registered: _ResolvedType) -> int:
    """Return the MRO distance from *actual* to *registered*.

    For a Union/tuple, returns the minimum distance across all member types.

    For Protocol types (which are not in the class MRO), returns a distance of
    ``len(actual.__mro__)`` so that concrete-type handlers are always ranked
    as more specific than Protocol handlers.

    Called only after ``matches()`` has confirmed the argument is an instance
    of *registered*, so a match is guaranteed.
    """
    if isinstance(registered, tuple):
        # For Union types take the minimum distance across all matching members
        best: int | None = None
        for member in registered:
            d = _mro_distance_single(actual, member)
            if best is None or d < best:
                best = d
        # At least one member matched (isinstance confirmed by matches())
        return best if best is not None else len(actual.__mro__)
    return _mro_distance_single(actual, registered)


def _mro_distance_single(actual: type[Any], target: type[Any]) -> int:
    """Return MRO distance from *actual* to *target*.

    If *target* is not in *actual*'s MRO (e.g. it is a structural Protocol),
    returns ``len(actual.__mro__)`` as a fallback "large" distance, ensuring
    plain-class handlers sort before Protocol handlers.
    """
    try:
        mro = actual.__mro__
    except AttributeError:
        return 0
    for i, cls in enumerate(mro):
        if cls is target:
            return i
    # Protocol or other structural type — use a value beyond the deepest MRO entry
    return len(mro)
