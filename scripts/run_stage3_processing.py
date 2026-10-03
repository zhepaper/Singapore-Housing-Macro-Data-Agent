#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.processing.models import load_frozen_data_plan
from housing_agent.processing.pipeline import run_stage3


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic Stage 3 processing from an approved frozen plan."
    )
    parser.add_argument("--plan", required=True, help="Path to frozen_data_plan.json")
    parser.add_argument("--output", required=True, help="Output directory for this run")
    args = parser.parse_args()

    plan = load_frozen_data_plan(args.plan)
    result = run_stage3(plan, Path(args.output))
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
