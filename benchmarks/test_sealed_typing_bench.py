from __future__ import annotations

from sealed_typing import assert_exhaustive, sealed


@sealed
class _Event:
    pass


class _Start(_Event):
    pass


class _Stop(_Event):
    pass


def test_sealed_assert_exhaustive(benchmark) -> None:
    result = benchmark(lambda: assert_exhaustive(_Start(), _Start, _Stop))
    assert result is None
