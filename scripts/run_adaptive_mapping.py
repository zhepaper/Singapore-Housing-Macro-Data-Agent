#!/usr/bin/env python3
"""Profile a preserved raw snapshot and generate a validated Mapping Contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.onboarding.mapping_agent import build_adaptive_mapping_graph  # noqa: E402


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-context", type=Path)
    parser.add_argument("--catalog-fragment", type=Path, action="append")
    parser.add_argument("--raw-snapshot-evidence", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--series-id")
    parser.add_argument("--frequency", choices=("monthly", "quarterly", "annual"))
    parser.add_argument("--provider", choices=("gemini", "openai", "anthropic", "deepseek"), default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    evidence_payload = json.loads(args.raw_snapshot_evidence.read_text(encoding="utf-8"))
    if isinstance(evidence_payload, list):
        matches = [item for item in evidence_payload if item.get("source_id") == args.source_id]
        if len(matches) != 1:
            parser.error("raw snapshot evidence must contain exactly one matching source_id")
        evidence_payload = matches[0]
    context = None
    if args.source_context:
        context = json.loads(args.source_context.read_text(encoding="utf-8"))
    if args.catalog_fragment:
        entries = []
        for path in args.catalog_fragment:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries.extend(payload.get("approved_entries", []))
        matches = [
            item["entry"] for item in entries
            if item["entry"]["source_id"] == args.source_id
        ]
        if len(matches) != 1:
            parser.error("catalog fragments must contain exactly one matching source_id")
        entry = matches[0]
        context = {
            "official_agency": entry["official_agency"],
            "dataset_title": entry["dataset_title"],
            "definition": entry["definition"],
            "unit": entry["unit"],
            "series_identifier": entry["series_identifier"],
            "exact_series_label": entry.get("exact_series_label"),
            "allowed_unit_scales": ["1"],
        }
        args.series_id = args.series_id or entry["predictor_id"]
        args.frequency = args.frequency or entry["native_frequency"]
    if context is None:
        parser.error("provide --source-context or at least one --catalog-fragment")
    if not args.series_id or not args.frequency:
        parser.error("series ID and frequency must be supplied or derivable from the catalog")
    result = build_adaptive_mapping_graph().invoke({
        "source_context": context,
        "source_id": args.source_id,
        "series_id": args.series_id,
        "observation_frequency": args.frequency,
        "raw_snapshot_evidence": evidence_payload,
        "mapping_provider": args.provider,
        "mapping_model": args.model,
        "max_mapping_attempts": args.max_attempts,
        "mapping_artifact_dir": str(args.output),
    })
    mapped = result["adaptive_mapping_result"]
    print(f"AdaptiveMapping status: {mapped['status']}")
    print(f"Attempts: {len(mapped['attempts'])}")
    print(f"Artifacts: {args.output.resolve()}")
    if args.print_summary and mapped.get("accepted_proposal"):
        print("\n" + json.dumps({
            "mapping_contract": mapped["accepted_proposal"]["mapping_contract"],
            "execution": mapped["accepted_execution"],
        }, indent=2, ensure_ascii=False))
    for error in mapped.get("errors", []):
        print(f"MAPPING ERROR: {error}", file=sys.stderr)
    return 0 if mapped["status"] == "ready_for_human_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
