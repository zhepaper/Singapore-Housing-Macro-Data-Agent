#!/usr/bin/env python3
"""Execute one human-approved preparation contract over normalized observations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.models import Observation  # noqa: E402
from housing_agent.preparation.execution import execute_preparation_contract  # noqa: E402
from housing_agent.preparation.models import PreparationContract  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--approved-plan", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.approved_plan.read_text())
    contract_data = next(
        (item for item in plan["contracts"] if item["source_id"] == args.source_id),
        None,
    )
    if contract_data is None:
        parser.error("source-id is not present in the human-approved plan")
    payload = json.loads(args.observations.read_text())
    rows = payload["observations"] if isinstance(payload, dict) else payload
    observations = [Observation(**item) for item in rows]
    output, trace = execute_preparation_contract(
        observations, PreparationContract.model_validate(contract_data)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "execution_trace": trace.model_dump(mode="json"),
        "observations": [item.to_dict() for item in output],
    }, indent=2) + "\n")
    print(f"Prepared observations: {len(output)}")
    print(f"Output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
