#!/usr/bin/env python3
"""Write the dependency set audited by ``make security``."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECTS = sorted(ROOT.glob("*/pyproject.toml"))
DOCS_REQUIREMENTS = ROOT / "docs" / "requirements.txt"
EXTRA_RELEASE_TOOLS = ("twine", "pkginfo")


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _requirement_name(requirement: str) -> str:
    token = requirement.strip()
    end = len(token)
    for marker in ("[", "<", ">", "=", "!", "~", ";", " "):
        pos = token.find(marker)
        if pos != -1:
            end = min(end, pos)
    return _normalize_name(token[:end])


def _collect_internal_projects() -> set[str]:
    names: set[str] = set()
    for pyproject in PYPROJECTS:
        data = tomllib.loads(pyproject.read_text())
        project = data.get("project", {})
        name = project.get("name")
        if isinstance(name, str):
            names.add(_normalize_name(name))
    return names


def _iter_declared_requirements() -> list[str]:
    requirements: list[str] = []
    for pyproject in PYPROJECTS:
        data = tomllib.loads(pyproject.read_text())
        project = data.get("project", {})
        requirements.extend(project.get("dependencies", []))
        optional = project.get("optional-dependencies", {})
        for values in optional.values():
            requirements.extend(values)
    if DOCS_REQUIREMENTS.exists():
        for line in DOCS_REQUIREMENTS.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                requirements.append(stripped)
    requirements.extend(EXTRA_RELEASE_TOOLS)
    return requirements


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: write_security_requirements.py OUTPUT_PATH", file=sys.stderr)
        return 2

    output_path = Path(sys.argv[1])
    internal_projects = _collect_internal_projects()
    requirements = sorted(
        {
            requirement
            for requirement in _iter_declared_requirements()
            if _requirement_name(requirement) not in internal_projects
        }
    )
    output_path.write_text("".join(f"{requirement}\n" for requirement in requirements))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
