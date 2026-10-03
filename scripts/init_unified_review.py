#!/usr/bin/env python3
"""Create an editable unified source, mapping, preparation, and role review template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-result", type=Path, action="append", required=True)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--plan-version", type=int, default=1)
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--historical-start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--historical-end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    decisions = []
    for path in args.mapping_result:
        payload = json.loads(path.read_text(encoding="utf-8"))
        mapped = payload.get("adaptive_mapping_result", payload)
        decisions.append({
            "source_id": mapped.get("source_id", "EDIT_SOURCE_ID"),
            "decision": "approve",
            "role_assignment": {
                "source_id": mapped.get("source_id", "EDIT_SOURCE_ID"),
                "series_id": mapped.get("series_id", "edit_series_id"),
                "series_label": "EDIT HUMAN-READABLE SERIES LABEL",
                "portfolio_role": "EDIT: outcome | predictor | structural_context",
                "market_role": "EDIT: sale | rent | shared",
                "release_lag_days": 0,
                "minimum_observations": 2,
                "max_staleness_periods": 4,
                "duplicate_policy": "error",
            },
            "review_notes": [
                "EDIT after reviewing raw snapshot, mapping execution, and preparation recommendation."
            ],
        })
    template = {
        "plan_id": args.plan_id,
        "plan_version": args.plan_version,
        "reviewer": "EDIT REVIEWER NAME",
        "confirmation_status": "draft",
        "reporting_as_of_date": args.as_of,
        "historical_start_date": args.historical_start,
        "historical_end_date": args.historical_end,
        "minimum_quarterly_observations": 8,
        "feature_redundancy_threshold": "0.95",
        "source_decisions": decisions,
        "overall_notes": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Edit and confirm: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
