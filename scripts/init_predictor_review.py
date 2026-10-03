#!/usr/bin/env python3
"""Create an editable human predictor-review submission from SearchNode output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proposal = json.loads(
        (args.search_output / "predictor_proposal.json").read_text()
    )
    submission = {
        "review_version": 1,
        "reviewer": "REPLACE_WITH_REVIEWER_NAME",
        "candidate_reviews": [
            {
                "predictor_id": item["predictor_id"],
                "decision": "REPLACE_WITH_approve_reject_OR_request_revision",
                "review_notes": [],
                "selection_rationale": [],
            }
            for item in proposal["candidates"]
        ],
        "overall_notes": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(submission, indent=2) + "\n")
    print(f"Edit every decision in: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
