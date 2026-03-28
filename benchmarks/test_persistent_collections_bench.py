from __future__ import annotations

from persistent_collections import PersistentMap, PersistentVector


def test_persistent_map_set_chain(benchmark) -> None:
    def build_map() -> PersistentMap[int, int]:
        m: PersistentMap[int, int] = PersistentMap()
        for i in range(128):
            m = m.set(i, i)
        return m

    result = benchmark(build_map)
    assert len(result) == 128


def test_persistent_vector_iteration(benchmark) -> None:
    vector = PersistentVector(range(1024))
    total = benchmark(lambda: sum(vector))
    assert total == sum(range(1024))

