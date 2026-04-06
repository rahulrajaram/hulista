"""DispatchActor — Actor subclass that routes messages via typed handler methods."""
# NOTE: Do NOT add `from __future__ import annotations` here.  We need
# annotations to remain plain runtime values (or be resolved before we assign
# them to wrappers) so that Dispatcher.register() can call get_type_hints()
# correctly.

import ast
import inspect
import sys
import typing
from typing import Any, Callable, ClassVar

from asyncio_actors.actor import Actor

_UNRESOLVED = object()


def _make_dispatcher(name: str) -> Any:
    """Import and return a new Dispatcher instance, or None if live-dispatch is unavailable."""
    try:
        from live_dispatch._dispatcher import Dispatcher
        return Dispatcher(name)
    except ImportError:
        return None


def _resolve_annotations_at_decoration(fn: Callable[..., Any]) -> dict[str, Any]:
    """Resolve string annotations for *fn* at decoration time.

    We grab the caller's local namespace via the call stack so that types
    defined in enclosing scopes (e.g., local variables in a test function)
    can be resolved — not just module-level globals.
    """
    # Walk up the call stack to collect every local + global namespace that
    # might contain the annotated types.  Start from the caller of the
    # decorator (frame depth 2 from here: 0=this func, 1=_HandleMarker.__init__
    # or handle(), 2=the class body, 3=enclosing scope).
    localns: dict[str, Any] = {}
    try:
        for depth in range(1, 10):
            frame = sys._getframe(depth)
            localns.update(frame.f_locals)
    except ValueError:
        pass  # ran out of frames

    globalns: dict[str, Any] = {}
    module = getattr(fn, "__module__", None)
    if module is not None:
        mod = sys.modules.get(module)
        if mod is not None:
            globalns = vars(mod)
    # Also include fn's own globals (same as module globals, but a safety net).
    fn_globals = getattr(fn, "__globals__", {})
    merged_globals = {**fn_globals, **globalns}

    try:
        hints = typing.get_type_hints(fn, globalns=merged_globals, localns=localns)
    except (NameError, AttributeError, TypeError):
        # Fall back: use the raw annotation dict (values may be strings).
        # Resolve only a narrow safe subset instead of executing annotation
        # expressions. Dispatch handlers only need runtime type objects.
        hints = {}
        raw = getattr(fn, "__annotations__", {})
        for k, v in raw.items():
            if k == "return":
                continue
            if isinstance(v, str):
                resolved = _resolve_string_annotation(v, merged_globals, localns)
                if resolved is not _UNRESOLVED:
                    hints[k] = resolved
            else:
                hints[k] = v
        return hints

    return {k: v for k, v in hints.items() if k != "return"}


def _resolve_string_annotation(
    annotation: str,
    globalns: dict[str, Any],
    localns: dict[str, Any],
) -> Any:
    """Resolve a safe subset of string annotations without using eval().

    Supported forms:
    - ``Name``
    - dotted attribute chains such as ``module.Type`` or ``Outer.Inner``
    - ``A | B`` unions
    - ``typing.Union[A, B]`` and ``typing.Optional[A]``
    """
    try:
        node = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return _UNRESOLVED
    return _resolve_annotation_node(node, globalns, localns)


def _resolve_annotation_node(
    node: ast.AST,
    globalns: dict[str, Any],
    localns: dict[str, Any],
) -> Any:
    if isinstance(node, ast.Name):
        return _lookup_annotation_name(node.id, globalns, localns)

    if isinstance(node, ast.Attribute):
        base = _resolve_annotation_node(node.value, globalns, localns)
        if base is _UNRESOLVED:
            return _UNRESOLVED
        return getattr(base, node.attr, _UNRESOLVED)

    if isinstance(node, ast.Constant) and node.value is None:
        return type(None)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _resolve_annotation_node(node.left, globalns, localns)
        right = _resolve_annotation_node(node.right, globalns, localns)
        if left is _UNRESOLVED or right is _UNRESOLVED:
            return _UNRESOLVED
        try:
            return left | right
        except TypeError:
            return _UNRESOLVED

    if isinstance(node, ast.Subscript):
        base = _resolve_annotation_node(node.value, globalns, localns)
        if base is _UNRESOLVED:
            return _UNRESOLVED
        args = _resolve_annotation_subscript_args(node.slice, globalns, localns)
        if args is _UNRESOLVED:
            return _UNRESOLVED
        if base is typing.Union:
            try:
                result = args[0]
                for part in args[1:]:
                    result = result | part
                return result
            except TypeError:
                return _UNRESOLVED
        if base is typing.Optional and len(args) == 1:
            try:
                return args[0] | type(None)
            except TypeError:
                return _UNRESOLVED
        return _UNRESOLVED

    return _UNRESOLVED


def _resolve_annotation_subscript_args(
    node: ast.AST,
    globalns: dict[str, Any],
    localns: dict[str, Any],
) -> tuple[Any, ...] | object:
    if isinstance(node, ast.Tuple):
        resolved = tuple(
            _resolve_annotation_node(item, globalns, localns)
            for item in node.elts
        )
        if any(item is _UNRESOLVED for item in resolved):
            return _UNRESOLVED
        return resolved

    resolved = _resolve_annotation_node(node, globalns, localns)
    if resolved is _UNRESOLVED:
        return _UNRESOLVED
    return (resolved,)


def _lookup_annotation_name(
    name: str,
    globalns: dict[str, Any],
    localns: dict[str, Any],
) -> Any:
    if name == "None":
        return type(None)
    if name in localns:
        return localns[name]
    if name in globalns:
        return globalns[name]
    typing_value = getattr(typing, name, _UNRESOLVED)
    if typing_value is not _UNRESOLVED:
        return typing_value
    return _UNRESOLVED


class _HandleMarker:
    """Wraps a handler method so __init_subclass__ can identify it.

    Eagerly resolves the handler's type annotations at decoration time so
    that local types (defined in enclosing function scopes) are captured
    before the decorator returns.
    """

    __slots__ = ("func", "resolved_hints")

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func
        # Resolve at decoration time — the enclosing frame is still live.
        self.resolved_hints: dict[str, Any] = _resolve_annotations_at_decoration(func)

    # Transparent attribute forwarding so the marker looks like the function
    # when accessed on a class body (before descriptor protocol kicks in).
    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        # Return the underlying function bound to obj.
        return self.func.__get__(obj, objtype)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        return self.func(*args, **kwargs)


class DispatchActor(Actor):
    """Actor that routes messages to type-annotated handler methods.

    Subclasses register handlers with the ``@DispatchActor.handle`` decorator.
    On class creation, the handlers are collected and registered with a per-class
    :class:`~live_dispatch.Dispatcher`.

    If ``message_type`` is set to a ``@sealed`` class, exhaustiveness of the
    registered handlers is verified at class-definition time.

    Usage::

        @sealed
        class Msg: pass
        class Ping(Msg): pass
        class Pong(Msg): pass

        class MyActor(DispatchActor):
            message_type = Msg  # optional: enables exhaustiveness check

            @DispatchActor.handle
            async def on_ping(self, msg: Ping) -> str:
                return "pong"

            @DispatchActor.handle
            async def on_pong(self, msg: Pong) -> str:
                return "ping"
    """

    #: Set to a ``@sealed`` base class to enable exhaustiveness checking.
    message_type: ClassVar[Any] = None

    # Per-subclass Dispatcher (set by __init_subclass__).
    _dispatcher: ClassVar[Any] = None

    # ------------------------------------------------------------------
    # Class-level machinery
    # ------------------------------------------------------------------

    @staticmethod
    def handle(func: Callable[..., Any]) -> "_HandleMarker":
        """Decorator that marks a method as a message handler."""
        return _HandleMarker(func)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        dispatcher = _make_dispatcher(cls.__qualname__)
        cls._dispatcher = dispatcher

        if dispatcher is None:
            # live-dispatch not available — skip registration but still allow
            # the class to be defined.  on_message will fall through to
            # on_unhandled for every message.
            return

        # Collect handlers defined on this subclass and its ancestors, walking
        # from the most-base class to the most-derived (reversed MRO) so that
        # more-derived overrides win when types overlap.
        for klass in reversed(cls.__mro__):
            if klass is DispatchActor or klass is Actor or klass is object:
                continue
            for attr_name, attr_val in klass.__dict__.items():
                if not isinstance(attr_val, _HandleMarker):
                    continue
                raw_func = attr_val.func
                # Use the already-resolved hints captured at decoration time.
                resolved_hints = attr_val.resolved_hints

                wrapper = _make_handler_wrapper(raw_func, resolved_hints)
                dispatcher.register(wrapper)

        # Exhaustiveness check when message_type is a sealed class.
        mt = cls.__dict__.get("message_type") or getattr(cls, "message_type", None)
        if mt is not None:
            try:
                if getattr(mt, "__sealed__", False):
                    dispatcher.verify_exhaustive(mt)
            except ImportError:
                pass  # sealed-typing not available; skip check silently.

    # ------------------------------------------------------------------
    # Runtime message routing
    # ------------------------------------------------------------------

    async def on_message(self, message: Any) -> Any:
        """Route *message* to the matching handler, or call on_unhandled."""
        dispatcher = type(self)._dispatcher
        if dispatcher is None:
            return await self.on_unhandled(message)

        try:
            return await dispatcher.call_async(self, message)
        except TypeError:
            return await self.on_unhandled(message)

    async def on_unhandled(self, message: Any) -> Any:
        """Called when no handler matches *message*.

        Override to provide custom fallback behaviour.  The default
        implementation raises :class:`TypeError`.
        """
        raise TypeError(
            "{} received unhandled message: {!r}".format(
                type(self).__name__, message
            )
        )


# ---------------------------------------------------------------------------
# Module-level helpers (defined outside the class so they are plain functions,
# not descriptors, and don't interfere with class-body scanning).
# ---------------------------------------------------------------------------

def _make_handler_wrapper(
    fn: Callable[..., Any],
    resolved_hints: dict[str, Any],
) -> Callable[..., Any]:
    """Return an async wrapper for *fn* with concrete (non-string) annotations.

    The wrapper preserves the original signature (including the ``self``
    parameter) but attaches resolved annotations so that Dispatcher can
    determine dispatch types via get_type_hints() without needing the
    original module's globals.

    ``self`` is annotated as ``object`` so that the Dispatcher accepts the
    parameter (all required params must be annotated once any is annotated)
    while still matching any actor instance.
    """
    sig = inspect.signature(fn)

    async def _wrapper(*args: Any, **kw: Any) -> Any:
        return await fn(*args, **kw)

    _wrapper.__name__ = fn.__name__
    _wrapper.__qualname__ = fn.__qualname__
    # Use *this* module so get_type_hints can find the annotations dict
    # without needing the subclass module's globals.
    _wrapper.__module__ = __name__

    # Build annotations dict: include `self: object` so the Dispatcher sees
    # all required params as typed, then the message param(s) with their
    # concrete types.  Note: we skip the "return" key.
    params = list(sig.parameters.keys())
    annotations: dict[str, Any] = {}
    if params:
        # First param is "self" — annotate as object so isinstance check passes
        # for any actor instance but doesn't restrict dispatch.
        annotations[params[0]] = object
    annotations.update(
        {k: v for k, v in resolved_hints.items()
         if k not in (params[:1] if params else [])}
    )

    _wrapper.__annotations__ = annotations
    try:
        _wrapper.__signature__ = sig  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        pass
    return _wrapper
