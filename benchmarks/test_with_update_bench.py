from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from with_update import updatable


@updatable
@dataclass(frozen=True)
class _Settings:
    retries: int = 3
    timeout: float = 0.5


@updatable
class _Config(BaseModel):
    host: str = "localhost"
    port: int = 5432


def test_with_update_dataclass_copy(benchmark) -> None:
    settings = _Settings()
    result = benchmark(lambda: settings.with_update(retries=4))
    assert result.retries == 4


def test_with_update_pydantic_copy(benchmark) -> None:
    config = _Config()
    result = benchmark(lambda: config.with_update(port=6432))
    assert result.port == 6432

