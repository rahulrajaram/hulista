"""Core implementation of @sealed decorator."""
from __future__ import annotations

import sys
from typing import Any


def sealed(cls: type) -> type:
    """Mark a class as sealed — only subclasses defined in the same module are allowed.

    Usage:
        @sealed
        class Shape:
            pass

        class Circle(Shape):  # OK — same module
            pass

        class Square(Shape):  # OK — same module
            pass

        # In another module:
        class Triangle(Shape):  # TypeError at class creation time
            pass
    """
    if not isinstance(cls, type):
        raise TypeError(f"@sealed can only be applied to classes, got {type(cls).__name__}")

    cls.__sealed__ = True
    cls.__sealed_module__ = cls.__module__
    cls.__sealed_subclasses__ = set()

    original_init_subclass = cls.__init_subclass__

    @classmethod
    def _sealed_init_subclass(subcls, **kwargs):
        # Allow subclassing only within the same module
        if subcls.__module__ != cls.__sealed_module__:
            raise TypeError(
                f"Cannot subclass sealed class '{cls.__qualname__}' "
                f"outside of module '{cls.__sealed_module__}'. "
                f"Attempted in module '{subcls.__module__}'."
            )
        cls.__sealed_subclasses__.add(subcls)
        # Call original __init_subclass__ if it existed
        if original_init_subclass is not type.__init_subclass__:
            original_init_subclass(**kwargs)

    cls.__init_subclass__ = _sealed_init_subclass

    # Register any subclasses that were defined before @sealed was applied
    # (handles the case where subclasses exist in the same module already)
    for existing_sub in cls.__subclasses__():
        if existing_sub.__module__ == cls.__sealed_module__:
            cls.__sealed_subclasses__.add(existing_sub)

    return cls


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

    expected = sealed_subclasses(sealed_base)
    provided = frozenset(handlers)
    missing = expected - provided

    if missing:
        missing_names = ', '.join(sorted(c.__qualname__ for c in missing))
        raise TypeError(
            f"Non-exhaustive match on sealed class '{sealed_base.__qualname__}'. "
            f"Missing handlers for: {missing_names}"
        )
