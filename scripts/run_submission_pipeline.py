#!/usr/bin/env python3
"""Run the reviewer-facing deterministic Stage 3 -> Stage 4 workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from housing_agent.processing.models import load_frozen_data_plan  # noqa: E402
from housing_agent.processing.pipeline import run_stage3  # noqa: E402
from housing_agent.report_generation.models import ReportBrief  # noqa: E402
from housing_agent.report_generation.pipeline import load_evidence_bundle, run_stage4  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Process the approved frozen data plan and generate a verified report from "
            "the resulting evidence bundle. No API key or network access is required."
        )
    )
    parser.add_argument(
        "--plan",
        default="config/frozen_data_plan.json",
        help="Approved FrozenDataPlan JSON.",
    )
    parser.add_argument(
        "--brief",
        default="config/report_brief.example.json",
        help="ReportBrief JSON containing qualitative rationale and citations.",
    )
    parser.add_argument(
        "--output",
        default="outputs/submission_run",
        help="Output directory for Stage 3 and Stage 4 artifacts.",
    )
    parser.add_argument("--print-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output)
    plan = load_frozen_data_plan(args.plan)

    stage3 = run_stage3(plan, output_root / "stage3")
    if stage3.status != "success" or not stage3.evidence_bundle_path:
        print("Submission workflow status: blocked")
        print("Stage 3 did not produce a validated evidence bundle.")
        print(json.dumps(stage3.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 1

    brief = ReportBrief.model_validate_json(Path(args.brief).read_text(encoding="utf-8"))
    evidence = load_evidence_bundle(stage3.evidence_bundle_path)
    stage4 = run_stage4(
        evidence,
        output_root / "stage4",
        brief=brief,
        provider="deterministic",
        max_attempts=3,
    )

    summary = {
        "status": "success" if stage4.status == "success" else "blocked",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "reporting_as_of_date": plan.reporting_as_of_date.isoformat(),
        "stage3_status": stage3.status,
        "evidence_bundle": "stage3/evidence/validated_evidence_bundle.json",
        "stage4_status": stage4.status,
        "report": "stage4/final_report.md",
        "verification": "stage4/verification_report.json",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "workflow_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Submission workflow status: {summary['status']}")
    print(f"Information cut-off: {summary['reporting_as_of_date']}")
    print(f"Evidence: {(output_root / summary['evidence_bundle']).resolve()}")
    print(f"Report: {(output_root / summary['report']).resolve()}")
    print(f"Verification: {(output_root / summary['verification']).resolve()}")
    print(f"Summary: {summary_path.resolve()}")
    if args.print_report and stage4.report_path:
        print()
        print(Path(stage4.report_path).read_text(encoding="utf-8"))
    return 0 if stage4.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
