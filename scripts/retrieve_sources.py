#!/usr/bin/env python3
"""Run the production retrieval layer without requiring the LangGraph runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.retrieval import retrieve_catalog_sources  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", action="append", dest="source_ids")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--request-interval", type=float, default=13.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args()

    catalog = json.loads((PROJECT_ROOT / "config/data_catalog.yaml").read_text())
    sources = catalog["sources"]
    if args.source_ids:
        requested = set(args.source_ids)
        sources = [source for source in sources if source["source_id"] in requested]
        missing = requested - {source["source_id"] for source in sources}
        if missing:
            raise ValueError(f"Unknown source IDs: {sorted(missing)}")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    results = retrieve_catalog_sources(
        sources,
        args.output_dir,
        request_interval_seconds=args.request_interval,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )
    for result in results:
        print(json.dumps(result.to_dict(), sort_keys=True), flush=True)
    return 0 if all(result.retrieval_status == "success" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
