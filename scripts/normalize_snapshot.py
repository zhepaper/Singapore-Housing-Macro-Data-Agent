#!/usr/bin/env python3
"""Normalize a preserved data.gov.sg snapshot to JSON Lines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.adapters.datagov import normalize_datagov  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_id")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    catalog = json.loads((PROJECT_ROOT / "config/data_catalog.yaml").read_text())
    matches = [source for source in catalog["sources"] if source["source_id"] == args.source_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one catalogue source for {args.source_id!r}")
    source = matches[0]
    if source["source_type"] != "datagov_json":
        raise ValueError("This command only handles data.gov.sg JSON snapshots")

    payload = json.loads(args.snapshot.read_text())
    observations = normalize_datagov(payload, source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(json.dumps(observation.to_dict(), separators=(",", ":")) + "\n")
    print(f"Wrote {len(observations)} observations to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

