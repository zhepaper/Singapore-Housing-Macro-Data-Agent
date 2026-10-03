#!/usr/bin/env python3
"""Re-run deterministic probes for a saved discovery proposal without an LLM call."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.onboarding.discovery import (  # noqa: E402
    build_draft_entries,
    validate_discovery,
)
from housing_agent.onboarding.discovery_models import load_discovery_proposal  # noqa: E402
from housing_agent.onboarding.discovery_tools import probe_data_source  # noqa: E402
from housing_agent.research.models import load_predictor_candidate  # noqa: E402


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-output", type=Path, required=True)
    parser.add_argument("--predictor-review-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proposal = load_discovery_proposal(
        json.loads((args.discovery_output / "discovery_proposal.json").read_text())
    )
    approved = json.loads(
        (args.predictor_review_output / "approved_predictors.json").read_text()
    )
    predictor_by_id = {
        item.predictor_id: item
        for item in (
            load_predictor_candidate(value)
            for value in approved["predictors"]
        )
    }
    if proposal.predictor_id not in predictor_by_id:
        raise ValueError("Saved discovery proposal is not for an approved predictor")
    probes = [probe_data_source(candidate) for candidate in proposal.candidates]
    validation = validate_discovery(
        proposal,
        predictor_by_id[proposal.predictor_id],
        probes,
    )
    drafts = build_draft_entries(proposal, validation, probes)
    _write(args.output / "discovery_proposal.json", proposal.model_dump(mode="json"))
    _write(args.output / "source_probes.json", [item.model_dump(mode="json") for item in probes])
    _write(args.output / "discovery_validation.json", validation.model_dump(mode="json"))
    _write(args.output / "draft_catalog_entries.json", {
        "catalog_status": "draft_unapproved",
        "entries": [item.model_dump(mode="json") for item in drafts],
    })
    _write(args.output / "reprobe_metadata.json", {
        "source_discovery_output": str(args.discovery_output.resolve()),
        "reprobed_at": datetime.now(timezone.utc).isoformat(),
        "llm_called": False,
    })
    print(f"Reprobe validation: {validation.automated_validation_status}")
    print(f"Human catalog review: {validation.human_review_status}")
    print(f"Draft entries: {len(drafts)}")
    print(f"Reprobe artifacts: {args.output.resolve()}")
    for error in validation.errors:
        print(f"REPROBE ERROR: {error}", file=sys.stderr)
    return 0 if validation.automated_validation_status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
