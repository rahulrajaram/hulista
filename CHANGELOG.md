# Changelog

All notable changes to this project will be documented in this file.

## 0.1.0 - 2026-04-05

Initial monorepo release for the hulista package family.

### Added

- `persistent-collections`: `PersistentMap` and `PersistentVector` with structural sharing, transient builders, structural diffing, and hashable immutable collections.
- `sealed-typing`: `@sealed`, sealed subclass tracking, and runtime exhaustiveness helpers for `match`/`case` workflows.
- `asyncio-actors`: OTP-inspired actor primitives with bounded inboxes, supervision trees, selective receive, circuit breakers, and async-sync bridge support.
- `taskgroup-collect`: `CollectorTaskGroup` with collect-all failure semantics instead of first-error sibling cancellation.
- `fp-combinators`: sync and async pipeline helpers, reusable pipelines, `Result`/`Ok`/`Err`, and typed error-aware combinators.
- `live-dispatch`: runtime type and predicate dispatch, async dispatch, rollbackable handler versioning, caching, and sealed-type exhaustiveness verification.
- `with-update`: `|` and `.with_update()` support for frozen dataclasses and Pydantic models with runtime field validation.
- `hulista`: umbrella meta-package that installs and re-exports the seven core libraries together.
