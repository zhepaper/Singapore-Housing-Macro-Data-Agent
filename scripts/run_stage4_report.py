#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from housing_agent.report_generation.models import ReportBrief  # noqa: E402
from housing_agent.report_generation.pipeline import load_evidence_bundle, run_stage4  # noqa: E402
from housing_agent.report_generation.memory_bridge import report_brief_from_memory  # noqa: E402
from housing_agent.memory.models import MemorySnapshot  # noqa: E402
from housing_agent.processing.models import load_frozen_data_plan  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and verify a Stage 4 report from a Stage 3 evidence bundle."
    )
    parser.add_argument("--evidence", required=True, help="validated_evidence_bundle.json")
    parser.add_argument("--output", required=True, help="Stage 4 output directory")
    parser.add_argument(
        "--provider",
        default="deterministic",
        choices=("deterministic", "gemini", "openai", "anthropic", "deepseek"),
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--brief", default=None, help="Optional ReportBrief JSON file")
    parser.add_argument("--memory", default=None, help="Optional compiled MemorySnapshot JSON")
    parser.add_argument("--plan", default=None, help="Optional FrozenDataPlan used to map memory predictor IDs")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--print-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    bundle = load_evidence_bundle(args.evidence)
    brief = None
    if args.brief:
        brief = ReportBrief.model_validate_json(Path(args.brief).read_text(encoding="utf-8"))
    if args.memory:
        memory = MemorySnapshot.model_validate_json(Path(args.memory).read_text(encoding="utf-8"))
        plan = load_frozen_data_plan(args.plan) if args.plan else None
        brief = report_brief_from_memory(memory, plan=plan, base=brief)
    result = run_stage4(
        bundle,
        args.output,
        brief=brief,
        provider=args.provider,
        model=args.model,
        max_attempts=args.max_attempts,
    )
    print(f"Stage 4 status: {result.status}")
    print(f"Attempts: {result.attempts}")
    print(f"Artifacts: {result.output_directory}")
    if result.report_path:
        print(f"Report: {result.report_path}")
        if args.print_report:
            print()
            print(Path(result.report_path).read_text(encoding="utf-8"))
    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"- {error}")
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
