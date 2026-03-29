# Contributing

## Local Checks

Run all commands from the repo root.

- `make test`: run the full monorepo test suite.
- `make coverage`: run the full suite with coverage gates. This must keep every package at `>=95%` line coverage and `>=90%` branch coverage.
- `make typecheck`: run the repo mypy gate across source packages and tooling scripts.
- `make deprecationcheck`: run the repo test/build paths with deprecation warnings promoted to errors.
- `make bench`: run the benchmark suite and compare results against checked-in budgets.
- `make build`: build sdists and wheels for all packages.

Use `/home/rahul/311/bin/python3` by default unless you are intentionally validating another interpreter.

## CI Expectations

The GitHub Actions workflow has six main jobs:

- `test`: package unit tests plus the top-level integration suite across the active Python matrix.
- `coverage`: the enforced coverage gate on Python 3.11.
- `typecheck`: the enforced mypy gate on Python 3.11.
- `deprecationcheck`: the enforced warnings-as-errors gate for repo tests and package builds on Python 3.11.
- `build`: wheel and sdist smoke builds for every package.
- `benchmark`: benchmark checks on Python 3.11.

The `benchmark` job only runs on `schedule` and `workflow_dispatch` because timing noise makes it a poor fit for every push. The `coverage` and `benchmark` jobs upload their JSON reports as workflow artifacts on scheduled and manual runs.

## Packaging Notes

All packages currently use `setuptools.build_meta`. Keep packaging changes consistent across packages unless there is a package-specific reason not to.

Source distributions intentionally exclude repo test suites and benchmark fixtures. Validate packaging changes with `make build` before merging.
