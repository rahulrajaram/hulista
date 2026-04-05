from __future__ import annotations

from fp_combinators import Ok, pipe


def test_fp_pipe_chain(benchmark) -> None:
    result = benchmark(
        lambda: pipe(1, lambda x: x + 1, lambda x: x * 2, lambda x: x - 3, abs)
    )
    assert result == 1


def test_fp_result_map_chain(benchmark) -> None:
    result = benchmark(lambda: Ok(1).map(lambda x: x + 1).map(lambda x: x * 3).unwrap())
    assert result == 6
