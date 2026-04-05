"""Tests for Result, Ok, Err, and try_pipe."""
from __future__ import annotations

import pytest

from fp_combinators._result import Result, Ok, Err, try_pipe


# ---------------------------------------------------------------------------
# Ok — creation and basic accessors
# ---------------------------------------------------------------------------

class TestOkCreation:
    def test_ok_stores_value(self):
        r = Ok(42)
        assert r.value == 42

    def test_ok_is_ok_true(self):
        assert Ok("hello").is_ok() is True

    def test_ok_is_err_false(self):
        assert Ok("hello").is_err() is False

    def test_ok_unwrap_returns_value(self):
        assert Ok(99).unwrap() == 99

    def test_ok_unwrap_or_returns_value_not_default(self):
        assert Ok(7).unwrap_or(0) == 7

    def test_ok_unwrap_err_raises(self):
        with pytest.raises(ValueError, match="unwrap_err"):
            Ok("oops").unwrap_err()

    def test_ok_is_truthy(self):
        assert bool(Ok(0)) is True       # even when value is falsy
        assert bool(Ok(None)) is True
        assert bool(Ok(False)) is True

    def test_ok_repr(self):
        assert repr(Ok(42)) == "Ok(42)"
        assert repr(Ok("hi")) == "Ok('hi')"


# ---------------------------------------------------------------------------
# Err — creation and basic accessors
# ---------------------------------------------------------------------------

class TestErrCreation:
    def test_err_stores_error(self):
        r = Err("something went wrong")
        assert r.error == "something went wrong"

    def test_err_is_err_true(self):
        assert Err("bad").is_err() is True

    def test_err_is_ok_false(self):
        assert Err("bad").is_ok() is False

    def test_err_unwrap_raises(self):
        with pytest.raises(ValueError, match="unwrap"):
            Err("oops").unwrap()

    def test_err_unwrap_error_message_contains_error(self):
        try:
            Err("my error").unwrap()
        except ValueError as exc:
            assert "my error" in str(exc)

    def test_err_unwrap_or_returns_default(self):
        assert Err("bad").unwrap_or(99) == 99

    def test_err_unwrap_err_returns_error(self):
        assert Err("the error").unwrap_err() == "the error"

    def test_err_is_falsy(self):
        assert bool(Err("x")) is False
        assert bool(Err(0)) is False
        assert bool(Err(None)) is False

    def test_err_repr(self):
        assert repr(Err("oops")) == "Err('oops')"
        assert repr(Err(404)) == "Err(404)"


# ---------------------------------------------------------------------------
# map / map_err
# ---------------------------------------------------------------------------

class TestMap:
    def test_map_on_ok_transforms_value(self):
        result = Ok(3).map(lambda x: x * 2)
        assert result == Ok(6)

    def test_map_on_err_passes_through(self):
        err = Err("bad")
        result = err.map(lambda x: x * 2)
        assert result is err

    def test_map_err_on_err_transforms_error(self):
        result = Err("bad").map_err(str.upper)
        assert result == Err("BAD")

    def test_map_err_on_ok_passes_through(self):
        ok = Ok(42)
        result = ok.map_err(str.upper)
        assert result is ok

    def test_map_chaining(self):
        result = Ok(2).map(lambda x: x + 1).map(lambda x: x * 10)
        assert result == Ok(30)

    def test_map_type_change(self):
        result = Ok(42).map(str)
        assert result == Ok("42")


# ---------------------------------------------------------------------------
# and_then / or_else
# ---------------------------------------------------------------------------

class TestAndThenOrElse:
    def test_and_then_ok_to_ok(self):
        result = Ok(5).and_then(lambda x: Ok(x + 1))
        assert result == Ok(6)

    def test_and_then_ok_to_err(self):
        result = Ok(-1).and_then(
            lambda x: Err("negative") if x < 0 else Ok(x)
        )
        assert result == Err("negative")

    def test_and_then_err_short_circuits(self):
        called = []
        err = Err("already failed")
        result = err.and_then(lambda x: called.append(x) or Ok(x))
        assert result is err
        assert called == []

    def test_or_else_err_to_ok(self):
        result = Err("bad").or_else(lambda e: Ok(0))
        assert result == Ok(0)

    def test_or_else_err_to_err(self):
        result = Err("original").or_else(lambda e: Err(f"wrapped: {e}"))
        assert result == Err("wrapped: original")

    def test_or_else_ok_passes_through(self):
        ok = Ok(42)
        result = ok.or_else(lambda e: Ok(0))
        assert result is ok

    def test_and_then_chaining(self):
        def safe_div(x):
            return Err("div by zero") if x == 0 else Ok(100 // x)

        assert Ok(5).and_then(safe_div) == Ok(20)
        assert Ok(0).and_then(safe_div) == Err("div by zero")
        assert Err("upstream").and_then(safe_div) == Err("upstream")


# ---------------------------------------------------------------------------
# __bool__ (truthy/falsy)
# ---------------------------------------------------------------------------

class TestBool:
    def test_ok_truthy_in_if(self):
        reached = False
        if Ok("yes"):
            reached = True
        assert reached

    def test_err_falsy_in_if(self):
        reached = True
        if Err("no"):
            reached = False
        assert reached

    def test_bool_used_in_filter(self):
        results = [Ok(1), Err("a"), Ok(2), Err("b"), Ok(3)]
        ok_values = [r.unwrap() for r in results if r]
        assert ok_values == [1, 2, 3]


# ---------------------------------------------------------------------------
# Frozen / immutable (dataclass frozen=True)
# ---------------------------------------------------------------------------

class TestFrozen:
    def test_ok_is_frozen(self):
        ok = Ok(10)
        with pytest.raises((AttributeError, TypeError)):
            ok.value = 99  # type: ignore[misc]

    def test_err_is_frozen(self):
        err = Err("oops")
        with pytest.raises((AttributeError, TypeError)):
            err.error = "changed"  # type: ignore[misc]

    def test_ok_is_hashable(self):
        # frozen dataclasses are hashable
        s = {Ok(1), Ok(2), Ok(1)}
        assert len(s) == 2

    def test_err_is_hashable(self):
        s = {Err("a"), Err("b"), Err("a")}
        assert len(s) == 2


# ---------------------------------------------------------------------------
# Result base-class isinstance checks
# ---------------------------------------------------------------------------

class TestResultIsInstance:
    def test_ok_is_result(self):
        assert isinstance(Ok(1), Result)

    def test_err_is_result(self):
        assert isinstance(Err("x"), Result)


# ---------------------------------------------------------------------------
# try_pipe — success paths
# ---------------------------------------------------------------------------

class TestTryPipeSuccess:
    def test_try_pipe_single_function(self):
        result = try_pipe("42", int)
        assert result == Ok(42)

    def test_try_pipe_multiple_functions(self):
        result = try_pipe("  hello  ", str.strip, str.upper, len)
        assert result == Ok(5)

    def test_try_pipe_no_functions_returns_ok(self):
        result = try_pipe(99)
        assert result == Ok(99)

    def test_try_pipe_lambda_chain(self):
        result = try_pipe(2, lambda x: x + 1, lambda x: x * 10)
        assert result == Ok(30)

    def test_try_pipe_returns_ok_type(self):
        result = try_pipe(1, lambda x: x)
        assert result.is_ok()

    def test_try_pipe_preserves_none_value(self):
        result = try_pipe(None, lambda x: x)
        assert result == Ok(None)


# ---------------------------------------------------------------------------
# try_pipe — failure paths
# ---------------------------------------------------------------------------

class TestTryPipeFailure:
    def test_try_pipe_catches_value_error(self):
        result = try_pipe("not-a-number", int)
        assert result.is_err()
        assert isinstance(result.unwrap_err(), ValueError)

    def test_try_pipe_catches_exception_from_middle_step(self):
        called_after = []
        result = try_pipe(
            "bad",
            int,                             # raises ValueError here
            lambda x: called_after.append(x) or x,  # must NOT be called
        )
        assert result.is_err()
        assert called_after == []

    def test_try_pipe_returns_err_type(self):
        result = try_pipe("bad", int)
        assert result.is_err()
        assert isinstance(result, Err)

    def test_try_pipe_catches_runtime_error(self):
        def boom(x):
            raise RuntimeError("explode!")

        result = try_pipe(5, boom)
        err = result.unwrap_err()
        assert isinstance(err, RuntimeError)
        assert "explode!" in str(err)

    def test_try_pipe_catches_exception_in_first_step(self):
        result = try_pipe([], lambda x: x[999])
        assert result.is_err()
        assert isinstance(result.unwrap_err(), IndexError)

    def test_try_pipe_err_value_is_the_exception(self):
        exc_msg = "specific error"
        result = try_pipe(0, lambda x: (_ for _ in ()).throw(ValueError(exc_msg)))
        # Alternative: use a helper
        def raiser(x):
            raise ValueError(exc_msg)

        result = try_pipe(0, raiser)
        assert isinstance(result.unwrap_err(), ValueError)
        assert exc_msg in str(result.unwrap_err())
