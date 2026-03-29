from __future__ import annotations

import builtins

import pytest

import with_update._core as core
from with_update import with_update


def test_is_pydantic_model_handles_missing_dependency(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "pydantic":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert core._is_pydantic_model(type("Plain", (), {})) is False


def test_with_update_rejects_plain_objects() -> None:
    class Plain:
        pass

    with pytest.raises(TypeError, match="dataclass or Pydantic"):
        with_update(Plain(), value=1)


def test_normalize_pydantic_changes_rejects_duplicate_aliases() -> None:
    pydantic = pytest.importorskip("pydantic")

    class Model(pydantic.BaseModel):
        model_config = {"populate_by_name": True}
        value: int = pydantic.Field(alias="VALUE")

    with pytest.raises(TypeError, match="Duplicate update keys"):
        core._normalize_pydantic_changes(Model, {"value": 1, "VALUE": 2})
