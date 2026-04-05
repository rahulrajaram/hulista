"""Tests for TaskOutcome <-> fp-combinators Result adapters."""

from __future__ import annotations

import pytest

from taskgroup_collect import Failure, Success
from taskgroup_collect import outcome_to_result, outcomes_to_results, result_to_outcome

# fp-combinators is required for these tests.
fp_combinators = pytest.importorskip("fp_combinators")

from fp_combinators import Err, Ok  # noqa: E402 — after importorskip


class TestOutcomeToResult:
    """outcome_to_result() converts TaskOutcome -> Result."""

    def test_success_to_ok(self) -> None:
        outcome = Success(42)
        result = outcome_to_result(outcome)
        assert isinstance(result, Ok)
        assert result.value == 42

    def test_failure_to_err(self) -> None:
        exc = ValueError("boom")
        outcome = Failure(exc)
        result = outcome_to_result(outcome)
        assert isinstance(result, Err)
        assert result.error is exc

    def test_round_trip_success(self) -> None:
        original = Success("hello")
        result = outcome_to_result(original)
        recovered = result_to_outcome(result)
        assert isinstance(recovered, Success)
        assert recovered.value == "hello"

    def test_round_trip_failure(self) -> None:
        exc = RuntimeError("round-trip")
        original = Failure(exc)
        result = outcome_to_result(original)
        recovered = result_to_outcome(result)
        assert isinstance(recovered, Failure)
        assert recovered.exception is exc


class TestResultToOutcome:
    """result_to_outcome() converts Result -> TaskOutcome."""

    def test_ok_to_success(self) -> None:
        result = Ok(99)
        outcome = result_to_outcome(result)
        assert isinstance(outcome, Success)
        assert outcome.value == 99

    def test_err_to_failure(self) -> None:
        exc = KeyError("missing")
        result = Err(exc)
        outcome = result_to_outcome(result)
        assert isinstance(outcome, Failure)
        assert outcome.exception is exc

    def test_non_exception_err_raises_type_error(self) -> None:
        """Err("string") must raise TypeError — not a BaseException."""
        result = Err("not-an-exception")
        with pytest.raises(TypeError, match="BaseException"):
            result_to_outcome(result)

    def test_non_exception_err_int_raises_type_error(self) -> None:
        """Err(42) must also raise TypeError."""
        result = Err(42)
        with pytest.raises(TypeError, match="BaseException"):
            result_to_outcome(result)


class TestOutcomesToResults:
    """outcomes_to_results() converts a list of TaskOutcome to a list of Result."""

    def test_mixed_outcomes_converted(self) -> None:
        exc = ValueError("bad")
        outcomes = [Success(1), Failure(exc), Success(3)]
        results = outcomes_to_results(outcomes)

        assert len(results) == 3
        assert isinstance(results[0], Ok)
        assert results[0].value == 1

        assert isinstance(results[1], Err)
        assert results[1].error is exc

        assert isinstance(results[2], Ok)
        assert results[2].value == 3

    def test_empty_list(self) -> None:
        results = outcomes_to_results([])
        assert results == []

    def test_all_success(self) -> None:
        outcomes = [Success(i) for i in range(4)]
        results = outcomes_to_results(outcomes)
        assert all(isinstance(r, Ok) for r in results)
        assert [r.value for r in results] == [0, 1, 2, 3]

    def test_all_failures(self) -> None:
        exceptions = [RuntimeError(str(i)) for i in range(3)]
        outcomes = [Failure(e) for e in exceptions]
        results = outcomes_to_results(outcomes)
        assert all(isinstance(r, Err) for r in results)
        assert [r.error for r in results] == exceptions
