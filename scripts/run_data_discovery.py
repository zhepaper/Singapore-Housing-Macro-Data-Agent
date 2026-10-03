#!/usr/bin/env python3
"""Discover and independently probe official data for one approved predictor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.onboarding.discovery import make_data_discovery_node  # noqa: E402


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictor-review-output", type=Path, required=True)
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--provider", choices=("gemini",), default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-search-tool-calls", type=int, default=12)
    parser.add_argument("--max-discovery-attempts", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    approved = json.loads(
        (args.predictor_review_output / "approved_predictors.json").read_text()
    )
    scope = json.loads(args.scope.read_text())
    result = make_data_discovery_node()({
        "approved_scope": scope,
        "approved_predictors": approved["predictors"],
        "target_predictor_id": args.target,
        "discovery_provider": args.provider,
        "discovery_model": args.model,
        "max_search_tool_calls": args.max_search_tool_calls,
        "max_discovery_attempts": args.max_discovery_attempts,
        "discovery_artifact_dir": str(args.output),
    })
    validation = result["discovery_validation"]
    print(f"DataDiscovery execution: {result['discovery_metadata']['execution_status']}")
    print(f"Automated validation: {validation['automated_validation_status']}")
    print(f"Human catalog review: {validation['human_review_status']}")
    print(f"Draft entries: {len(result['draft_catalog_entries'])}")
    print(f"Discovery artifacts: {args.output.resolve()}")
    for warning in validation.get("warnings", []):
        print(f"DISCOVERY WARNING: {warning}", file=sys.stderr)
    for error in result["discovery_errors"] + validation.get("errors", []):
        print(f"DISCOVERY ERROR: {error}", file=sys.stderr)
    if result["discovery_errors"]:
        return 1
    return 0 if validation["automated_validation_status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
