#!/usr/bin/env python3
"""Apply an explicit human predictor-review submission to SearchNode artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.onboarding.review import review_predictors_node  # noqa: E402


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-output", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--memory-decision-log",
        type=Path,
        default=PROJECT_ROOT / "config/project_memory.seed.jsonl",
        help="Append the approved predictor decision and rationale to project memory.",
    )
    args = parser.parse_args()
    search = args.search_output
    request = _read(search / "research_request.json")
    result = review_predictors_node({
        "approved_scope": request["approved_scope"],
        "research_proposal": _read(search / "predictor_proposal.json"),
        "research_validation": _read(search / "research_validation.json"),
        "predictor_review_submission": _read(args.submission),
        "predictor_review_artifact_dir": str(args.output),
        "memory_decision_log_path": str(args.memory_decision_log),
    })
    review = result["predictor_review_result"]
    print(f"Predictor review: {review['review_status']}")
    print(f"Approved predictors: {', '.join(review['approved_predictor_ids']) or 'none'}")
    print(f"Review artifacts: {args.output.resolve()}")
    for error in review["errors"]:
        print(f"REVIEW ERROR: {error}", file=sys.stderr)
    return 0 if review["review_status"] == "approved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
