#!/usr/bin/env python3
"""Run the fixed quality eval set and record pass rate/cost.

The runner accepts a JSON result per case from an external worker adapter. It
also supports a deterministic dry run so CI can validate the eval contract
without provider keys or media files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if len(cases) != 10:
        raise ValueError(f"Expected exactly 10 eval cases, found {len(cases)}")
    return cases


def evaluate_case(case: dict[str, Any], result: dict[str, Any]) -> tuple[bool, list[str]]:
    failures = []
    for check in case["checks"]:
        if not bool(result.get("checks", {}).get(check, False)):
            failures.append(check)
    return not failures, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", default="evals/quality_eval_set.json")
    parser.add_argument("--results", help="JSON object keyed by case id")
    parser.add_argument("--out", default="quality-eval-results.json")
    args = parser.parse_args()
    cases = load_cases(Path(args.eval_set))
    supplied = json.loads(Path(args.results).read_text(encoding="utf-8")) if args.results else {}
    rows = []
    for case in cases:
        # Dry runs intentionally fail closed: CI proves the suite is wired,
        # while a real worker supplies evidence for each check.
        result = supplied.get(case["id"], {"checks": {}})
        passed, failures = evaluate_case(case, result)
        rows.append({"id": case["id"], "passed": passed, "failures": failures, "cost_usd": float(result.get("cost_usd", 0))})
    passed = sum(1 for row in rows if row["passed"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pass_rate": passed / len(rows),
        "passed": passed,
        "total": len(rows),
        "cost_usd": sum(row["cost_usd"] for row in rows),
        "cases": rows,
        "model": os.getenv("AGENT_MODEL", "claude-opus-5-5"),
    }
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
