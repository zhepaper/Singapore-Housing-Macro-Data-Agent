#!/usr/bin/env python3
"""Create an editable human review from preparation-advisor output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisor-output", type=Path, required=True)
    parser.add_argument("--plan-version", default="preparation-1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proposal = json.loads(
        (args.advisor_output / "preparation_proposal.json").read_text(encoding="utf-8")
    )
    submission = {
        "plan_version": args.plan_version,
        "reviewer": "REPLACE_WITH_REVIEWER_NAME",
        "review_choice": "approve_all",
        "custom_instructions": None,
        "confirmation_status": "draft",
        "source_reviews": [
            {
                "source_id": item["contract"]["source_id"],
                "decision": "REPLACE_WITH_approve_reject_OR_request_revision",
                "approved_contract": item["contract"],
                "review_notes": [],
            }
            for item in proposal["recommendations"]
        ],
        "overall_notes": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8")
    print(f"Choose a review option, edit any contracts, and confirm in: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
