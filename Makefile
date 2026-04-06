PYTHON ?= python3
ROOT := $(abspath .)
PYTHONPATH := $(ROOT)/asyncio-actors:$(ROOT)/fp-combinators:$(ROOT)/live-dispatch:$(ROOT)/persistent-collections:$(ROOT)/sealed-typing:$(ROOT)/taskgroup-collect:$(ROOT)/with-update:$(ROOT)/hulista
PACKAGE_TESTS := \
	$(ROOT)/asyncio-actors \
	$(ROOT)/fp-combinators \
	$(ROOT)/live-dispatch \
	$(ROOT)/persistent-collections \
	$(ROOT)/sealed-typing \
	$(ROOT)/taskgroup-collect \
	$(ROOT)/with-update \
	$(ROOT)/hulista \
	$(ROOT)/tests
BENCHMARK_TESTS := $(ROOT)/benchmarks
BUILD_PACKAGES := \
	asyncio-actors \
	fp-combinators \
	live-dispatch \
	persistent-collections \
	sealed-typing \
	taskgroup-collect \
	with-update \
	hulista
SECURITY_SOURCE_DIRS := \
	asyncio-actors/asyncio_actors \
	fp-combinators/fp_combinators \
	hulista/hulista \
	live-dispatch/live_dispatch \
	persistent-collections/persistent_collections \
	sealed-typing/sealed_typing \
	taskgroup-collect/taskgroup_collect \
	with-update/with_update
PYTEST_DEPRECATION_FLAGS := -W error::DeprecationWarning -W error::PendingDeprecationWarning
BUILD_DEPRECATION_FLAGS := -W error::DeprecationWarning -W error::PendingDeprecationWarning -W error::UserWarning:setuptools

.PHONY: test coverage typecheck bench build deprecationcheck security docs-build docs-serve

test:
	PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -m pytest -p no:pytest_monitor $(PACKAGE_TESTS) -q

coverage:
	mkdir -p .benchmarks
	PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -m pytest -p no:pytest_monitor --cov=asyncio_actors --cov=fp_combinators --cov=live_dispatch --cov=persistent_collections --cov=sealed_typing --cov=taskgroup_collect --cov=with_update --cov-branch --cov-config=.coveragerc --cov-report=term-missing --cov-report=json:.benchmarks/coverage.json $(PACKAGE_TESTS) -q
	$(PYTHON) scripts/check_coverage.py .benchmarks/coverage.json

typecheck:
	MYPYPATH="$(PYTHONPATH)" $(PYTHON) -m mypy --config-file mypy.ini
	MYPYPATH="$(PYTHONPATH)" $(PYTHON) -m mypy --config-file mypy-tests.ini

bench:
	mkdir -p .benchmarks
	PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -m pytest $(BENCHMARK_TESTS) --benchmark-only --benchmark-json=.benchmarks/benchmark-results.json -q
	$(PYTHON) scripts/check_benchmarks.py .benchmarks/benchmark-results.json benchmarks/budgets.toml

build:
	for pkg in $(BUILD_PACKAGES); do \
		(cd $$pkg && $(PYTHON) -m build .); \
	done

deprecationcheck:
	PYTHONPATH="$(PYTHONPATH)" $(PYTHON) $(PYTEST_DEPRECATION_FLAGS) -m pytest -p no:pytest_monitor $(PACKAGE_TESTS) -q
	for pkg in $(BUILD_PACKAGES); do \
		(cd $$pkg && $(PYTHON) $(BUILD_DEPRECATION_FLAGS) -m build .); \
	done

security:
	$(PYTHON) -m bandit -q -r $(SECURITY_SOURCE_DIRS)
	tmpfile="$$(mktemp)"; \
	$(PYTHON) scripts/write_security_requirements.py "$$tmpfile"; \
	$(PYTHON) -m pip_audit -r "$$tmpfile"; \
	rm -f "$$tmpfile"

docs-build:
	$(PYTHON) -m mkdocs build --strict

docs-serve:
	$(PYTHON) -m mkdocs serve
