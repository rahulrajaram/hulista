# Changelog

All notable changes to this project will be documented in this file.

## 0.1.2 - 2026-04-25

### Fixed

- `persistent-collections`: ship `persistent_set.pyi` so `PersistentSet[T]` annotations stop tripping Pyright's `reportInvalidTypeArguments`. The runtime class shipped in 0.1.1 but no type stub, so downstream typed projects had to suppress the diagnostic per call site or drop typing. Stub mirrors the existing `persistent_vector.pyi` shape (`Generic[T] + collections.abc.Set[T]`, `iterable: object | None = ...`).

## 0.1.1 - 2026-04-19

### Fixed

- `hulista`: wheel now ships the top-level `hulista` package. In 0.1.0 a misconfigured `[tool.hatch.build.targets.wheel]` `packages` path caused Hatch to silently skip the meta-package, so `from hulista import Result, PersistentMap, sealed, ...` (the documented primary API) raised `ModuleNotFoundError` on every fresh install. Editable installs masked the bug, so it reached PyPI. Reported by the `selfimprove` agent via gptqueue.

### Added

- CI: release workflow now installs the built wheel into a clean venv and imports the top-level `hulista` API as a smoke test, so a broken meta-package wheel cannot reach PyPI again.

## 0.1.0 - 2026-04-05

Initial monorepo release for the hulista package family.

### Added

- `fp-combinators`: `async_sequence`, `async_traverse`, and `async_traverse_all` — sequential async Result helpers for ordered validation chains and async batch processing.
- `taskgroup-collect`: `collect_results()` convenience wrapper for concurrent fan-out, plus `outcome_to_result()`, `result_to_outcome()`, and `outcomes_to_results()` TaskOutcome↔Result adapters bridging taskgroup-collect and fp-combinators.
- `persistent-collections`: `freeze()` and `thaw()` recursive converters between plain Python dicts/lists and PersistentMap/PersistentVector, enabling gradual migration of mutable data structures.
- `live-dispatch`: CLOS-inspired method combinations (`:before`, `:after`, `:around`) with traced execution support, plus strengthened sealed-type exhaustiveness verification with per-parameter and auto-discovery modes.
- `sealed-typing`: `verify_dispatch_exhaustive()` convenience function for verifying live-dispatch handler coverage of sealed hierarchies.
- `persistent-collections`: `PersistentMap` and `PersistentVector` with structural sharing, transient builders, structural diffing, and hashable immutable collections.
- `sealed-typing`: `@sealed`, sealed subclass tracking, and runtime exhaustiveness helpers for `match`/`case` workflows.
- `asyncio-actors`: OTP-inspired actor primitives with bounded inboxes, supervision trees, selective receive, circuit breakers, and async-sync bridge support.
- `taskgroup-collect`: `CollectorTaskGroup` with collect-all failure semantics instead of first-error sibling cancellation.
- `fp-combinators`: sync and async pipeline helpers, reusable pipelines, `Result`/`Ok`/`Err`, and typed error-aware combinators.
- `live-dispatch`: runtime type and predicate dispatch, async dispatch, rollbackable handler versioning, caching, and sealed-type exhaustiveness verification.
- `with-update`: `|` and `.with_update()` support for frozen dataclasses and Pydantic models with runtime field validation.
- `hulista`: umbrella meta-package that installs and re-exports the seven core libraries together.
