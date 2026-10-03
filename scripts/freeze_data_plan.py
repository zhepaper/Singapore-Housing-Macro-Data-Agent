#!/usr/bin/env python3
"""Evaluate unified human approval and freeze the complete Stage 3 data plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.onboarding.plan_freezer import unified_plan_review_node  # noqa: E402


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-fragment", type=Path, action="append", required=True)
    parser.add_argument("--raw-snapshot-evidence", type=Path, required=True)
    parser.add_argument("--mapping-result", type=Path, action="append", required=True)
    parser.add_argument("--preparation-plan", type=Path, required=True)
    parser.add_argument("--review-submission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--print-review", action="store_true")
    args = parser.parse_args()

    sources = []
    for path in args.catalog_fragment:
        payload = _read(path)
        if payload.get("catalog_status") != "human_approved_fragment":
            parser.error(f"{path} is not a human-approved catalog fragment")
        sources.extend(payload["approved_entries"])
    snapshots = _read(args.raw_snapshot_evidence)
    if isinstance(snapshots, dict) and "raw_snapshot_evidence" in snapshots:
        snapshots = snapshots["raw_snapshot_evidence"]
    mappings = []
    for path in args.mapping_result:
        payload = _read(path)
        mappings.append(payload.get("adaptive_mapping_result", payload))
    preparation = _read(args.preparation_plan)
    contracts = preparation.get("contracts", preparation.get("approved_preparation_contracts", preparation))
    result = unified_plan_review_node({
        "approved_catalog_entries": sources,
        "raw_snapshot_evidence": snapshots,
        "adaptive_mapping_results": mappings,
        "approved_preparation_contracts": contracts,
        "unified_review_submission": _read(args.review_submission),
        "unified_review_artifact_dir": str(args.output),
    })
    review = result["unified_review_result"]
    print(f"Unified review: {review['status']}")
    print(f"Frozen plan: {review.get('frozen_plan_path') or 'not created'}")
    print(f"Artifacts: {args.output.resolve()}")
    if args.print_review:
        print("\n" + result["unified_review_markdown"])
    for error in review.get("errors", []):
        print(f"REVIEW ERROR: {error}", file=sys.stderr)
    return 0 if review["status"] == "approved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
