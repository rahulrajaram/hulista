"""Helper utilities for sealed-typing integration with live-dispatch."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from live_dispatch._dispatcher import _Handler, _ResolvedType


def _iter_types_in_spec(resolved: "_ResolvedType") -> list[type[Any]]:
    """Yield all concrete types contained in a resolved type-spec value."""
    if isinstance(resolved, tuple):
        return [t for t in resolved if isinstance(t, type)]
    if isinstance(resolved, type):
        return [resolved]
    return []


def _find_sealed_bases(handlers: "list[_Handler]") -> set[type[Any]]:
    """Scan all handlers' type_specs and return the set of sealed base classes.

    A sealed base is a class whose ``__sealed__`` attribute is ``True``
    (set by ``@sealed`` from sealed-typing).  We walk the MRO of every type
    that appears in any handler's type_spec, collecting classes that are
    themselves sealed bases.
    """
    sealed_bases: set[type[Any]] = set()
    for handler in handlers:
        for resolved in handler.type_spec.values():
            for t in _iter_types_in_spec(resolved):
                for ancestor in t.__mro__:
                    if ancestor.__dict__.get("__sealed__", False) is True:
                        sealed_bases.add(ancestor)
    return sealed_bases


def _covered_types_for_param(
    handlers: "list[_Handler]",
    param_name: str,
) -> set[type[Any]]:
    """Return the set of all types registered for *param_name* across handlers.

    Only handlers that have an explicit type annotation for *param_name* are
    considered.
    """
    covered: set[type[Any]] = set()
    for handler in handlers:
        resolved = handler.type_spec.get(param_name)
        if resolved is None:
            continue
        for t in _iter_types_in_spec(resolved):
            covered.add(t)
    return covered


def _params_referencing_sealed(
    handlers: "list[_Handler]",
    sealed_base: type[Any],
) -> set[str]:
    """Return parameter names whose annotations reference *sealed_base* or any
    of its registered subclasses.
    """
    sealed_subs: frozenset[type[Any]] = frozenset(
        getattr(sealed_base, "__sealed_subclasses__", set())
    )
    relevant_types = sealed_subs | {sealed_base}

    param_names: set[str] = set()
    for handler in handlers:
        for param_name, resolved in handler.type_spec.items():
            for t in _iter_types_in_spec(resolved):
                if t in relevant_types:
                    param_names.add(param_name)
                    break
    return param_names
