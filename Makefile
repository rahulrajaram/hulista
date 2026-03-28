PYTHON ?= /home/rahul/311/bin/python3
ROOT := $(abspath .)
PYTHONPATH := $(ROOT)/asyncio-actors:$(ROOT)/fp-combinators:$(ROOT)/live-dispatch:$(ROOT)/persistent-collections:$(ROOT)/sealed-typing:$(ROOT)/taskgroup-collect:$(ROOT)/with-update
PACKAGE_TESTS := \
	$(ROOT)/asyncio-actors \
	$(ROOT)/fp-combinators \
	$(ROOT)/live-dispatch \
	$(ROOT)/persistent-collections \
	$(ROOT)/sealed-typing \
	$(ROOT)/taskgroup-collect \
	$(ROOT)/with-update \
	$(ROOT)/tests
BENCHMARK_TESTS := $(ROOT)/benchmarks
BUILD_PACKAGES := \
	asyncio-actors \
	fp-combinators \
	live-dispatch \
	persistent-collections \
	sealed-typing \
	taskgroup-collect \
	with-update

.PHONY: test coverage typecheck bench build

test:
	PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -m pytest -p no:pytest_monitor $(PACKAGE_TESTS) -q

coverage:
	mkdir -p .benchmarks
	PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -m pytest -p no:pytest_monitor --cov=asyncio_actors --cov=fp_combinators --cov=live_dispatch --cov=persistent_collections --cov=sealed_typing --cov=taskgroup_collect --cov=with_update --cov-branch --cov-config=.coveragerc --cov-report=term-missing --cov-report=json:.benchmarks/coverage.json $(PACKAGE_TESTS) -q
	$(PYTHON) scripts/check_coverage.py .benchmarks/coverage.json

typecheck:
	MYPYPATH="$(PYTHONPATH)" $(PYTHON) -m mypy --config-file mypy.ini

bench:
	mkdir -p .benchmarks
	PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -m pytest $(BENCHMARK_TESTS) --benchmark-only --benchmark-json=.benchmarks/benchmark-results.json -q
	$(PYTHON) scripts/check_benchmarks.py .benchmarks/benchmark-results.json benchmarks/budgets.toml

build:
	for pkg in $(BUILD_PACKAGES); do \
		(cd $$pkg && $(PYTHON) -m build .); \
	done

