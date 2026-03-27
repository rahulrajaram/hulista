"""Core implementation of @updatable decorator."""
from __future__ import annotations

import dataclasses
from typing import Any


def _is_pydantic_model(cls: type) -> bool:
    """Check if cls is a Pydantic BaseModel subclass."""
    try:
        from pydantic import BaseModel
        return issubclass(cls, BaseModel)
    except ImportError:
        return False


def _make_or(cls: type, valid_fields: frozenset[str]):
    """Create __or__ method appropriate for the class type."""
    is_dc = dataclasses.is_dataclass(cls)
    is_pydantic = _is_pydantic_model(cls)

    def __or__(self, changes):
        if not isinstance(changes, dict):
            return NotImplemented
        invalid = set(changes.keys()) - valid_fields
        if invalid:
            raise TypeError(
                f"Invalid field(s) for {type(self).__qualname__}: "
                f"{', '.join(sorted(invalid))}. "
                f"Valid fields: {', '.join(sorted(valid_fields))}"
            )
        if is_dc:
            return dataclasses.replace(self, **changes)
        elif is_pydantic:
            return self.model_copy(update=changes)
        return NotImplemented

    return __or__


def _make_with_update():
    """Create with_update method."""
    def with_update(self, **changes: Any):
        """Return a new instance with the specified fields updated."""
        return self | changes
    return with_update


def updatable(cls: type) -> type:
    """Decorator that adds | operator and .with_update() for immutable record updates.

    Works with frozen dataclasses and Pydantic BaseModel subclasses.

    Usage:
        @updatable
        @dataclass(frozen=True)
        class Point:
            x: int
            y: int

        p = Point(1, 2)
        p2 = p | {"x": 10}       # Point(x=10, y=2)
        p3 = p.with_update(y=20)  # Point(x=1, y=20)
    """
    is_dc = dataclasses.is_dataclass(cls)
    is_pydantic = _is_pydantic_model(cls)

    if not (is_dc or is_pydantic):
        raise TypeError(
            f"@updatable requires a dataclass or Pydantic BaseModel, "
            f"got {cls.__qualname__}"
        )

    # Cache valid field names at decoration time
    if is_dc:
        valid_fields = frozenset(f.name for f in dataclasses.fields(cls))
    elif is_pydantic:
        valid_fields = frozenset(cls.model_fields.keys())
    else:
        valid_fields = frozenset()

    cls.__or__ = _make_or(cls, valid_fields)
    cls.with_update = _make_with_update()

    return cls


def with_update(self, **changes: Any):
    """Standalone function version: with_update(obj, field=value)."""
    if dataclasses.is_dataclass(self):
        return dataclasses.replace(self, **changes)
    if _is_pydantic_model(type(self)):
        return self.model_copy(update=changes)
    raise TypeError(
        f"with_update requires a dataclass or Pydantic model instance, "
        f"got {type(self).__qualname__}"
    )
