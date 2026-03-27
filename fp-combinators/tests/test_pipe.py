import pytest
from fp_combinators import pipe, compose, first_some, pipeline


def test_pipe_single():
    assert pipe(5, str) == "5"


def test_pipe_chain():
    assert pipe("hello", str.upper, len) == 5


def test_pipe_no_funcs():
    assert pipe(42) == 42


def test_compose_basic():
    f = compose(str, lambda x: x + 1)
    assert f(5) == "6"


def test_compose_single():
    f = compose(str)
    assert f(42) == "42"


def test_compose_empty_raises():
    with pytest.raises(TypeError):
        compose()


def test_first_some_basic():
    def none1(x): return None
    def none2(x): return None
    def found(x): return x * 2
    def never(x): raise AssertionError("should not be called")

    check = first_some(none1, none2, found, never)
    assert check(5) == 10


def test_first_some_all_none():
    def none1(x): return None
    def none2(x): return None

    check = first_some(none1, none2)
    assert check(5) is None


def test_first_some_empty_raises():
    with pytest.raises(TypeError):
        first_some()


def test_pipeline_basic():
    p = pipeline(str.strip, str.upper, len)
    assert p("  hello  ") == 5


def test_pipeline_single():
    p = pipeline(str.upper)
    assert p("hello") == "HELLO"


def test_pipeline_empty_raises():
    with pytest.raises(TypeError):
        pipeline()


def test_pipe_with_lambdas():
    result = pipe(
        [3, 1, 4, 1, 5],
        sorted,
        lambda xs: xs[:3],
        sum,
    )
    assert result == 1 + 1 + 3


def test_compose_qualname():
    f = compose(str, int)
    assert 'str' in f.__qualname__
    assert 'int' in f.__qualname__
