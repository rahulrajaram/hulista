"""Core implementation of @sealed decorator."""
from __future__ import annotations

import types
from collections.abc import Callable
from typing import Any, Union, cast, overload


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _module_name_of(obj: Union[types.ModuleType, str]) -> str:
    """Return the dotted module name for a module object or a string."""
    if isinstance(obj, types.ModuleType):
        return obj.__name__
    if isinstance(obj, str):
        return obj
    raise TypeError(
        f"permits entries must be modules or module-name strings, "
        f"got {type(obj).__name__!r}"
    )


def _is_allowed_module(
    submodule: str,
    *,
    sealed_module: str,
    permits: frozenset[str] | None,
    scope: str | None,
) -> bool:
    """Return True if *submodule* is permitted to subclass the sealed class.

    Resolution order (first match wins):
    1. Same module as the sealed class — always allowed.
    2. ``scope="package"`` — any module sharing the top-level package of the
       sealed class is allowed.
    3. An explicit ``permits`` set — the submodule must equal one of the
       listed names or must start with ``<name>.`` (treating each entry as a
       package prefix when it refers to a package).
    """
    if submodule == sealed_module:
        return True

    if scope == "package":
        # Top-level package is everything before the first dot.
        top = sealed_module.split(".")[0]
        return submodule == top or submodule.startswith(top + ".")

    if permits is not None:
        for permitted in permits:
            # Exact module match.
            if submodule == permitted:
                return True
            # Package prefix match: "myapp.core" permits "myapp.core.models".
            if submodule.startswith(permitted + "."):
                return True

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@overload
def sealed(cls: type) -> type: ...

@overload
def sealed(
    cls: None = ...,
    *,
    permits: list[Union[types.ModuleType, str]] | None = ...,
    scope: str | None = ...,
) -> Callable[[type], type]: ...


def sealed(
    cls: type | None = None,
    *,
    permits: list[Union[types.ModuleType, str]] | None = None,
    scope: str | None = None,
) -> type | Callable[[type], type]:
    """Mark a class as sealed — restrict where subclasses may be defined.

    Calling styles
    --------------
    Bare decorator (same-module restriction, backward-compatible):

        @sealed
        class Shape:
            pass

    With an explicit permits list:

        @sealed(permits=[module_a, "mypackage.messages"])
        class Event:
            pass

    With package-scoped convenience:

        @sealed(scope="package")
        class Command:
            pass

    Parameters
    ----------
    cls:
        The class to seal. Supplied automatically when ``@sealed`` is used
        without parentheses.
    permits:
        Optional list of :class:`types.ModuleType` objects or dotted module
        name strings.  A subclass is allowed if its ``__module__`` equals one
        of the listed names **or** starts with one of them followed by ``"."``.
        The sealed class's own module is always implicitly permitted.
    scope:
        When set to ``"package"``, any module that shares the same top-level
        package as the sealed class is permitted.  For example, if the class
        lives in ``myapp.core``, then ``myapp``, ``myapp.models``, and
        ``myapp.core.helpers`` are all allowed.

    Raises
    ------
    TypeError
        At class-definition time if a subclass is defined in a module that is
        not permitted.
    ValueError
        If *scope* is set to an unrecognised value.
    """
    if scope is not None and scope != "package":
        raise ValueError(
            f"Unsupported scope value {scope!r}. "
            "Currently only scope=\"package\" is supported."
        )

    def _apply(target: type) -> type:
        if not isinstance(target, type):
            raise TypeError(
                f"@sealed can only be applied to classes, got {type(target).__name__}"
            )

        target_any = cast(Any, target)
        target_any.__sealed__ = True
        target_any.__sealed_module__ = target.__module__
        target_any.__sealed_subclasses__ = set()

        # Resolve permits to a frozenset of strings once so the check inside
        # __init_subclass__ is cheap.
        resolved_permits: frozenset[str] | None = (
            frozenset(_module_name_of(p) for p in permits)
            if permits is not None
            else None
        )
        target_any.__sealed_permits__ = resolved_permits
        target_any.__sealed_scope__ = scope

        original_init_subclass = target.__dict__.get('__init_subclass__')
        original_init_subclass_func = getattr(
            original_init_subclass, '__func__', original_init_subclass
        )

        def _sealed_init_subclass(subcls: type, /, **kwargs: Any) -> None:
            allowed = _is_allowed_module(
                subcls.__module__,
                sealed_module=target_any.__sealed_module__,
                permits=target_any.__sealed_permits__,
                scope=target_any.__sealed_scope__,
            )
            if not allowed:
                if target_any.__sealed_permits__ is not None:
                    permitted_list = ", ".join(
                        repr(p) for p in sorted(target_any.__sealed_permits__)
                    )
                    raise TypeError(
                        f"Cannot subclass sealed class '{target.__qualname__}' "
                        f"from module '{subcls.__module__}'. "
                        f"Permitted modules: {target_any.__sealed_module__!r}"
                        f" + [{permitted_list}]."
                    )
                elif target_any.__sealed_scope__ == "package":
                    top = target_any.__sealed_module__.split(".")[0]
                    raise TypeError(
                        f"Cannot subclass sealed class '{target.__qualname__}' "
                        f"from module '{subcls.__module__}'. "
                        f"Permitted scope: package '{top}'."
                    )
                else:
                    raise TypeError(
                        f"Cannot subclass sealed class '{target.__qualname__}' "
                        f"outside of module '{target_any.__sealed_module__}'. "
                        f"Attempted in module '{subcls.__module__}'."
                    )

            other_sealed_bases = [
                base
                for base in subcls.__mro__[1:]
                if base is not target and is_sealed(base)
            ]
            if other_sealed_bases:
                names = ', '.join(base.__qualname__ for base in other_sealed_bases)
                raise TypeError(
                    f"Cannot create '{subcls.__qualname__}' with multiple sealed bases. "
                    f"Conflicting sealed base(s): {names}"
                )
            target_any.__sealed_subclasses__.add(subcls)
            # Call original __init_subclass__ if it existed.
            if original_init_subclass_func is not None:
                original_init_subclass_func(subcls, **kwargs)
            else:
                super(target, subcls).__init_subclass__(**kwargs)  # type: ignore[arg-type]

        target_any.__init_subclass__ = classmethod(_sealed_init_subclass)

        # Register any subclasses that were defined before @sealed was applied
        # (handles the case where subclasses exist in the same module already).
        for existing_sub in target.__subclasses__():
            if _is_allowed_module(
                existing_sub.__module__,
                sealed_module=target_any.__sealed_module__,
                permits=resolved_permits,
                scope=scope,
            ):
                target_any.__sealed_subclasses__.add(existing_sub)

        return target

    # Support both @sealed and @sealed(...) call styles.
    if cls is not None:
        # Called as @sealed (no parentheses) — cls is the decorated class.
        return _apply(cls)

    # Called as @sealed(...) — return the decorator.
    return _apply


def is_sealed(cls: type) -> bool:
    """Check if a class is sealed.

    Only returns True if the class itself was decorated with @sealed,
    not if it merely inherits from a sealed class.
    """
    return cls.__dict__.get('__sealed__', False) is True


def sealed_subclasses(cls: type) -> frozenset[type]:
    """Return all registered sealed subclasses of a class.

    Returns frozenset for hashability and immutability.
    """
    if not is_sealed(cls):
        raise TypeError(f"'{cls.__qualname__}' is not a sealed class")
    return frozenset(getattr(cls, '__sealed_subclasses__', set()))


def verify_dispatch_exhaustive(dispatcher: Any, sealed_base: type) -> None:
    """Verify that a live-dispatch Dispatcher covers all sealed subclasses.

    This is a thin convenience wrapper that calls
    ``dispatcher.verify_exhaustive(sealed_base)``.  It exists so
    sealed-typing users can verify dispatch coverage without importing
    live-dispatch directly.

    Args:
        dispatcher: A ``live_dispatch.Dispatcher`` instance (or any object
                    that exposes a ``verify_exhaustive`` method).
        sealed_base: A class decorated with ``@sealed``.

    Raises:
        TypeError: If *dispatcher* does not have a ``verify_exhaustive``
                   method, or if the dispatcher does not fully cover all
                   registered subclasses of *sealed_base*.
    """
    if not hasattr(dispatcher, 'verify_exhaustive'):
        raise TypeError(
            f"Expected a Dispatcher with a 'verify_exhaustive' method, "
            f"got {type(dispatcher).__name__!r}"
        )
    dispatcher.verify_exhaustive(sealed_base)


def assert_exhaustive(value: Any, *handlers: type) -> None:
    """Assert that handlers cover all sealed subclasses.

    Usage:
        def process(shape: Shape) -> float:
            match shape:
                case Circle(r=r):
                    return 3.14 * r * r
                case Square(s=s):
                    return s * s
            # At end of match, verify exhaustiveness:
            assert_exhaustive(shape, Circle, Square)

    Raises TypeError if value's base sealed class has subclasses not in handlers.
    """
    # Find the sealed base class
    cls = type(value)
    sealed_base = None

    for base in cls.__mro__:
        if is_sealed(base):
            sealed_base = base
            break

    if sealed_base is None:
        raise TypeError(
            f"'{cls.__qualname__}' is not a subclass of any sealed class"
        )

    invalid_handlers = [
        handler for handler in handlers
        if not isinstance(handler, type) or not issubclass(handler, sealed_base)
    ]
    if invalid_handlers:
        invalid_names = ', '.join(
            h.__qualname__ if isinstance(h, type) else repr(h)
            for h in invalid_handlers
        )
        raise TypeError(
            f"Handlers for sealed class '{sealed_base.__qualname__}' must be "
            f"subclasses of that sealed base. Invalid handlers: {invalid_names}"
        )

    expected = set(sealed_subclasses(sealed_base))
    if cls is sealed_base:
        expected.add(sealed_base)
    provided = frozenset(handlers)
    missing = frozenset(
        candidate for candidate in expected
        if not any(issubclass(candidate, handler) for handler in provided)
    )

    if missing:
        missing_names = ', '.join(sorted(c.__qualname__ for c in missing))
        raise TypeError(
            f"Non-exhaustive match on sealed class '{sealed_base.__qualname__}'. "
            f"Missing handlers for: {missing_names}"
        )
