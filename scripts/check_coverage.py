from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

LINE_THRESHOLD = 95.0
BRANCH_THRESHOLD = 90.0

PACKAGE_PREFIXES = {
    "asyncio-actors": "asyncio-actors/asyncio_actors/",
    "fp-combinators": "fp-combinators/fp_combinators/",
    "live-dispatch": "live-dispatch/live_dispatch/",
    "persistent-collections": "persistent-collections/persistent_collections/",
    "sealed-typing": "sealed-typing/sealed_typing/",
    "taskgroup-collect": "taskgroup-collect/taskgroup_collect/",
    "with-update": "with-update/with_update/",
}


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 100.0
    return numerator * 100.0 / denominator


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_coverage.py COVERAGE_JSON", file=sys.stderr)
        return 2

    report_path = Path(sys.argv[1])
    data = json.loads(report_path.read_text())
    files = cast(dict[str, dict[str, Any]], data["files"])

    failing = False
    for label, prefix in PACKAGE_PREFIXES.items():
        covered_lines = 0
        num_statements = 0
        covered_branches = 0
        num_branches = 0
        for path_str, payload in files.items():
            path = path_str.replace("\\", "/")
            if prefix not in path:
                continue
            summary = cast(dict[str, int], payload["summary"])
            covered_lines += int(summary["covered_lines"])
            num_statements += int(summary["num_statements"])
            covered_branches += int(summary["covered_branches"])
            num_branches += int(summary["num_branches"])

        line_rate = _rate(covered_lines, num_statements)
        branch_rate = _rate(covered_branches, num_branches)
        print(
            f"{label}: lines={line_rate:.2f}% ({covered_lines}/{num_statements}) "
            f"branches={branch_rate:.2f}% ({covered_branches}/{num_branches})"
        )
        if line_rate < LINE_THRESHOLD or branch_rate < BRANCH_THRESHOLD:
            failing = True

    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
