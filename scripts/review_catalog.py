#!/usr/bin/env python3
"""Apply human review to probed draft catalog entries without changing production."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.onboarding.catalog_review import catalog_review_node  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-output", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    drafts = json.loads(
        (args.discovery_output / "draft_catalog_entries.json").read_text()
    )
    submission = json.loads(args.submission.read_text())
    result = catalog_review_node({
        "draft_catalog_entries": drafts["entries"],
        "catalog_review_submission": submission,
        "catalog_review_artifact_dir": str(args.output),
    })
    review = result["catalog_review_result"]
    print(f"Catalog review: {review['review_status']}")
    print(f"Approved candidates: {', '.join(review['approved_candidate_ids']) or 'none'}")
    print(f"Review artifacts: {args.output.resolve()}")
    for error in review["errors"]:
        print(f"CATALOG REVIEW ERROR: {error}", file=sys.stderr)
    return 0 if review["review_status"] == "approved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
