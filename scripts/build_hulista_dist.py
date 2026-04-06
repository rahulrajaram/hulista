from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HULISTA_DIR = ROOT / "hulista"
GENERATED_PATHS = [
    HULISTA_DIR / "asyncio-actors",
    HULISTA_DIR / "fp-combinators",
    HULISTA_DIR / "live-dispatch",
    HULISTA_DIR / "persistent-collections",
    HULISTA_DIR / "sealed-typing",
    HULISTA_DIR / "taskgroup-collect",
    HULISTA_DIR / "with-update",
    HULISTA_DIR / "hulista" / "hulista",
    HULISTA_DIR / "hulista" / "tests",
]


def _cleanup_generated_paths() -> None:
    for path in GENERATED_PATHS:
        if path.exists():
            shutil.rmtree(path)


def _run_build(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "build", *args, "."],
        cwd=HULISTA_DIR,
        check=True,
    )


def main() -> int:
    _cleanup_generated_paths()
    try:
        _run_build("--sdist")
        _run_build("--wheel")
    finally:
        _cleanup_generated_paths()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
