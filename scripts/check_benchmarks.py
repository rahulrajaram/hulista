from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_benchmarks.py BENCHMARK_JSON BUDGETS_TOML", file=sys.stderr)
        return 2

    report_path = Path(sys.argv[1])
    budgets_path = Path(sys.argv[2])
    report = json.loads(report_path.read_text())
    budgets = tomllib.loads(budgets_path.read_text())
    defaults = budgets.get("defaults", {})
    default_max_mean_s = float(defaults.get("max_mean_s", 1.0))

    by_name = {}
    for entry in report["benchmarks"]:
        name = entry["name"]
        by_name[name] = entry
        if name.startswith("test_"):
            by_name[name.removeprefix("test_")] = entry
    failing = False

    for name, settings in budgets.get("benchmarks", {}).items():
        max_mean_s = float(settings.get("max_mean_s", default_max_mean_s))
        if name not in by_name:
            print(f"missing benchmark result for {name}", file=sys.stderr)
            failing = True
            continue
        mean_s = float(by_name[name]["stats"]["mean"])
        status = "ok" if mean_s <= max_mean_s else "slow"
        print(f"{status}: {name} mean={mean_s:.6f}s budget={max_mean_s:.6f}s")
        if mean_s > max_mean_s:
            failing = True

    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
