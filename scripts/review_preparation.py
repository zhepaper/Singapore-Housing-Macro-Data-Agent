#!/usr/bin/env python3
"""Approve explicit preparation contracts and append the decision to memory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.preparation.review import preparation_review_node  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisor-output", type=Path, required=True)
    parser.add_argument("--catalog-fragment", type=Path, action="append", required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--memory-decision-log", type=Path,
        default=PROJECT_ROOT / "config/project_memory.seed.jsonl",
    )
    args = parser.parse_args()
    entries = []
    for path in args.catalog_fragment:
        entries.extend(json.loads(path.read_text())["approved_entries"])
    result = preparation_review_node({
        "preparation_proposal": json.loads(
            (args.advisor_output / "preparation_proposal.json").read_text()
        ),
        "preparation_validation": json.loads(
            (args.advisor_output / "preparation_validation.json").read_text()
        ),
        "approved_catalog_entries": entries,
        "preparation_review_submission": json.loads(args.submission.read_text()),
        "preparation_review_artifact_dir": str(args.output),
        "memory_decision_log_path": str(args.memory_decision_log),
    })
    review = result["preparation_review_result"]
    print(f"Preparation review: {review['review_status']}")
    print(f"Approved contracts: {len(review['approved_contracts'])}")
    print(f"Artifacts: {args.output.resolve()}")
    for error in review["errors"]:
        print(f"REVIEW ERROR: {error}", file=sys.stderr)
    return 0 if review["review_status"] == "approved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
