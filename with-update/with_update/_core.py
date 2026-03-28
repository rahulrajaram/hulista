"""Core implementation of @updatable decorator."""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast


class _PydanticField(Protocol):
    alias: str | None


def _is_pydantic_model(cls: type[Any]) -> bool:
    """Check if cls is a Pydantic BaseModel subclass."""
    try:
        from pydantic import BaseModel
        return issubclass(cls, BaseModel)
    except ImportError:
        return False


def _valid_fields_for_type(cls: type[Any]) -> frozenset[str]:
    """Return the updateable field names for a supported record type."""
    if dataclasses.is_dataclass(cls):
        return frozenset(f.name for f in dataclasses.fields(cls) if f.init)
    if _is_pydantic_model(cls):
        return frozenset(_pydantic_allowed_change_keys(cls))
    return frozenset()


def _validate_changes(valid_fields: frozenset[str], changes: dict[str, Any], owner: str) -> None:
    """Raise a consistent error for invalid update fields."""
    invalid = set(changes.keys()) - valid_fields
    if invalid:
        raise TypeError(
            f"Invalid field(s) for {owner}: "
            f"{', '.join(sorted(invalid))}. "
            f"Valid fields: {', '.join(sorted(valid_fields))}"
        )


def _apply_updates(self: Any, changes: dict[str, Any], valid_fields: frozenset[str]) -> Any:
    """Apply validated updates to a dataclass or Pydantic model."""
    if dataclasses.is_dataclass(self):
        _validate_changes(valid_fields, changes, type(self).__qualname__)
        return dataclasses.replace(cast(Any, self), **changes)
    if _is_pydantic_model(type(self)):
        _validate_changes(valid_fields, changes, type(self).__qualname__)
        cls = type(self)
        canonical_changes, payload_changes = _normalize_pydantic_changes(cls, changes)
        data = self.model_dump(by_alias=True, round_trip=True)
        data.update(payload_changes)
        model = cls.model_validate(data)
        if hasattr(self, "__pydantic_private__"):
            private = getattr(self, "__pydantic_private__")
            if private is not None:
                object.__setattr__(model, "__pydantic_private__", dict(private))
        if hasattr(self, "model_fields_set"):
            object.__setattr__(
                model,
                "__pydantic_fields_set__",
                set(self.model_fields_set) | set(canonical_changes),
            )
        return model
    raise TypeError(
        f"with_update requires a dataclass or Pydantic model instance, "
        f"got {type(self).__qualname__}"
    )


def _pydantic_config_allows_field_names(cls: type[Any]) -> bool:
    config = cast(Mapping[str, Any], getattr(cls, "model_config", {}) or {})
    return bool(config.get("populate_by_name") or config.get("validate_by_name"))


def _pydantic_allowed_change_keys(cls: type[Any]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    allow_field_names = _pydantic_config_allows_field_names(cls)
    model_fields = cast(dict[str, _PydanticField], getattr(cls, "model_fields"))
    for name, field in model_fields.items():
        alias = field.alias
        if alias:
            allowed[alias] = name
        if alias is None or allow_field_names:
            allowed[name] = name
    return allowed


def _normalize_pydantic_changes(
    cls: type[Any],
    changes: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = _pydantic_allowed_change_keys(cls)
    canonical_changes: dict[str, Any] = {}
    payload_changes: dict[str, Any] = {}
    model_fields = cast(dict[str, _PydanticField], getattr(cls, "model_fields"))
    for raw_key, value in changes.items():
        field_name = allowed[raw_key]
        if field_name in canonical_changes and raw_key != field_name:
            raise TypeError(
                f"Duplicate update keys for {cls.__qualname__}: {raw_key} conflicts with {field_name}"
            )
        canonical_changes[field_name] = value
        field = model_fields[field_name]
        payload_key = field.alias or field_name
        payload_changes[payload_key] = value
    return canonical_changes, payload_changes


def _make_or(valid_fields: frozenset[str]) -> Callable[[Any, Any], Any]:
    """Create __or__ method appropriate for the class type."""
    def __or__(self: Any, changes: Any) -> Any:
        if not isinstance(changes, dict):
            return NotImplemented
        return _apply_updates(self, changes, valid_fields)

    return __or__


def _make_with_update() -> Callable[..., Any]:
    """Create with_update method."""
    def with_update(self: Any, **changes: Any) -> Any:
        """Return a new instance with the specified fields updated."""
        return self | changes
    return with_update


def updatable(cls: type[Any]) -> type[Any]:
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
    valid_fields = _valid_fields_for_type(cls)

    if "__or__" in cls.__dict__:
        raise TypeError(f"@updatable refuses to overwrite existing __or__ on {cls.__qualname__}")
    if "with_update" in cls.__dict__:
        raise TypeError(
            f"@updatable refuses to overwrite existing with_update() on {cls.__qualname__}"
        )

    setattr(cls, "__or__", _make_or(valid_fields))
    setattr(cls, "with_update", _make_with_update())

    return cls


def with_update(self: Any, **changes: Any) -> Any:
    """Standalone function version: with_update(obj, field=value)."""
    return _apply_updates(self, changes, _valid_fields_for_type(type(self)))
