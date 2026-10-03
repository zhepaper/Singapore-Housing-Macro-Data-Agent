#!/usr/bin/env python3
"""Preserve approved raw sources before any Mapping Contract is available."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.onboarding.models import load_approved_catalog_entry  # noqa: E402
from housing_agent.preparation.raw_capture import capture_unmapped_raw_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-fragment", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = []
    for path in args.catalog_fragment:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("catalog_status") != "human_approved_fragment":
            parser.error(f"{path} is not a human-approved catalog fragment")
        entries.extend(load_approved_catalog_entry(item) for item in payload["approved_entries"])
    raw_dir = args.output / "raw"
    evidence = [
        capture_unmapped_raw_snapshot(item, snapshot_directory=raw_dir)
        for item in entries
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    evidence_path = args.output / "raw_snapshot_evidence.json"
    evidence_path.write_text(
        json.dumps([item.model_dump(mode="json") for item in evidence], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Sources captured: {sum(item.status == 'pass' for item in evidence)}/{len(evidence)}")
    print(f"Evidence: {evidence_path.resolve()}")
    for item in evidence:
        for error in item.errors:
            print(f"{item.source_id}: {error}", file=sys.stderr)
    return 0 if all(item.status == "pass" for item in evidence) else 2


if __name__ == "__main__":
    raise SystemExit(main())
