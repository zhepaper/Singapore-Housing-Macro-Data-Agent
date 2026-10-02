#!/usr/bin/env python3
"""Run the LangGraph workflow over preserved official-source snapshots."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.run_context import load_latest_checkpoint, load_run  # noqa: E402
from housing_agent.workflow import build_graph  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, dest="as_of")
    parser.add_argument("--output", type=Path, default=Path("outputs/report.md"))
    parser.add_argument("--mode", choices=("live", "snapshots"), default="live")
    parser.add_argument("--request-interval", type=float, default=13.0)
    parser.add_argument("--resume-run-id")
    parser.add_argument("--allow-cached-fallback", action="store_true")
    parser.add_argument("--writer", choices=("deterministic", "openai"), default="deterministic")
    parser.add_argument("--writer-model", default="gpt-5-mini")
    parser.add_argument("--max-revisions", type=int, default=2)
    args = parser.parse_args()

    if args.resume_run_id:
        paths, manifest = load_run(PROJECT_ROOT, args.resume_run_id)
        if manifest["status"] != "running":
            raise ValueError(f"Only a running workflow can resume; status={manifest['status']}")
        stage, initial_state = load_latest_checkpoint(paths)
        next_node = {
            "retrieved": "normalize",
            "normalized": "transform",
            "transformed": "validate",
            "validated": "build_evidence",
        }.get(stage)
        if next_node is None:
            raise ValueError(f"Checkpoint stage is not resumable: {stage}")
        result = build_graph(resume_from=next_node).invoke(initial_state)
    else:
        result = build_graph().invoke({
            "reporting_as_of_date": args.as_of,
            "project_root": str(PROJECT_ROOT),
            "execution_mode": args.mode,
            "request_interval_seconds": args.request_interval,
            "allow_cached_fallback": args.allow_cached_fallback,
            "writer_mode": args.writer,
            "writer_model": args.writer_model,
            "max_revisions": args.max_revisions,
        })
    if result["run_status"] == "failed":
        for error in result.get("validation_errors", []):
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    run_report = Path(result["run_paths"]["report"]) / "report.md"
    output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(run_report, output)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
