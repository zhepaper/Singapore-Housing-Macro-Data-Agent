#!/usr/bin/env python3
"""Run the LangGraph workflow over preserved official-source snapshots."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.workflow import build_graph  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, dest="as_of")
    parser.add_argument("--output", type=Path, default=Path("outputs/report.md"))
    args = parser.parse_args()

    result = build_graph().invoke({
        "reporting_as_of_date": args.as_of,
        "project_root": str(PROJECT_ROOT),
    })
    if result["workflow_status"] == "blocked":
        for error in result.get("validation_errors", []):
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result["report_markdown"], encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

