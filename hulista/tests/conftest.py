from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_NAMES = (
    "asyncio_actors",
    "fp_combinators",
    "live_dispatch",
    "persistent_collections",
    "sealed_typing",
    "taskgroup_collect",
    "with_update",
)

MONOREPO_PACKAGE_ROOTS = (
    "asyncio-actors",
    "fp-combinators",
    "live-dispatch",
    "persistent-collections",
    "sealed-typing",
    "taskgroup-collect",
    "with-update",
    "hulista",
)


def _project_roots() -> tuple[Path, ...]:
    here = Path(__file__).resolve()
    return (here.parents[1], here.parents[2])


def _all_packages_present(root: Path) -> bool:
    return all((root / name).is_dir() for name in PACKAGE_NAMES)


def _configure_import_path() -> None:
    for root in _project_roots():
        if _all_packages_present(root):
            sys.path.insert(0, str(root))
            return

        monorepo_paths = [root / package_root for package_root in MONOREPO_PACKAGE_ROOTS]
        if all(path.is_dir() for path in monorepo_paths):
            for path in reversed(monorepo_paths):
                sys.path.insert(0, str(path))
            return


_configure_import_path()
