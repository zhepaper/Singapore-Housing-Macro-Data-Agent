#!/usr/bin/env python3
"""Recommend reviewable data-preparation contracts from memory and approved sources."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.memory.compiler import compile_memory, persist_memory_snapshot  # noqa: E402
from housing_agent.memory.store import DecisionLogStore  # noqa: E402
from housing_agent.preparation.advisor import build_data_preparation_advisor_graph  # noqa: E402


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog-fragment", type=Path, action="append", required=True,
        help="Approved catalog fragment; repeat for multiple discovery slices.",
    )
    parser.add_argument(
        "--memory-decision-log", type=Path,
        default=PROJECT_ROOT / "config/project_memory.seed.jsonl",
    )
    parser.add_argument("--provider", choices=("gemini",), default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-preparation-attempts", type=int, default=2)
    parser.add_argument(
        "--raw-snapshot-evidence", type=Path,
        help="Reuse preserved raw snapshot evidence from adaptive onboarding.",
    )
    parser.add_argument(
        "--mapping-result", type=Path, action="append",
        help="Validated adaptive mapping result; repeat once per source.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    approved_entries = []
    for path in args.catalog_fragment:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("catalog_status") != "human_approved_fragment":
            parser.error(f"{path} is not a human-approved catalog fragment")
        approved_entries.extend(payload["approved_entries"])
    memory, manifest = compile_memory(
        DecisionLogStore(args.memory_decision_log).load()
    )
    manifest = persist_memory_snapshot(memory, manifest, args.output / "project_memory")
    state = {
        "memory_snapshot": memory.model_dump(mode="json"),
        "memory_manifest": manifest.model_dump(mode="json"),
        "approved_catalog_entries": approved_entries,
        "preparation_provider": args.provider,
        "preparation_model": args.model,
        "max_preparation_attempts": args.max_preparation_attempts,
        "preparation_artifact_dir": str(args.output),
    }
    if args.raw_snapshot_evidence:
        snapshots = json.loads(args.raw_snapshot_evidence.read_text(encoding="utf-8"))
        if isinstance(snapshots, dict) and "raw_snapshot_evidence" in snapshots:
            snapshots = snapshots["raw_snapshot_evidence"]
        state["raw_snapshot_evidence"] = snapshots
    if args.mapping_result:
        executions = []
        for path in args.mapping_result:
            payload = json.loads(path.read_text(encoding="utf-8"))
            mapped = payload.get("adaptive_mapping_result", payload)
            if not mapped.get("accepted_execution"):
                parser.error(f"{path} has no accepted mapping execution")
            executions.append(mapped["accepted_execution"])
        state["mapping_execution_reports"] = executions
    result = build_data_preparation_advisor_graph().invoke(state)
    validation = result["preparation_validation"]
    print(f"PreparationAdvisor execution: {result['preparation_metadata']['execution_status']}")
    print(f"Automated validation: {validation['automated_validation_status']}")
    print(f"Human review: {validation['human_review_status']}")
    print(f"Artifacts: {args.output.resolve()}")
    if args.print_summary and result["preparation_proposal"]:
        print("\n" + result["preparation_review_view"]["markdown"])
    for error in result["preparation_errors"] + validation.get("errors", []):
        print(f"PREPARATION ERROR: {error}", file=sys.stderr)
    if result["preparation_errors"]:
        return 1
    return 0 if validation["automated_validation_status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
