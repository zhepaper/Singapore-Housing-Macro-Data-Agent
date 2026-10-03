#!/usr/bin/env python3
"""Create an editable human catalog-review submission from discovery output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-output", type=Path, required=True)
    parser.add_argument("--catalog-version", default="discovery-1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    drafts = json.loads(
        (args.discovery_output / "draft_catalog_entries.json").read_text()
    )
    submission = {
        "catalog_version": args.catalog_version,
        "reviewer": "REPLACE_WITH_REVIEWER_NAME",
        "candidate_reviews": [
            {
                "candidate_id": item["candidate_id"],
                "decision": "REPLACE_WITH_approve_reject_OR_request_revision",
                "review_notes": [],
            }
            for item in drafts["entries"]
        ],
        "overall_notes": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(submission, indent=2) + "\n")
    print(f"Edit every decision in: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
