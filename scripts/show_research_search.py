#!/usr/bin/env python3
"""Render an existing SearchNode result as citation-rich academic prose."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.research.models import (  # noqa: E402
    ResearchValidationResult,
    load_research_proposal,
)
from housing_agent.research.rendering import (  # noqa: E402
    render_academic_research_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Existing SearchNode artifact directory.",
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output

    proposal_path = output / "predictor_proposal.json"
    validation_path = output / "research_validation.json"
    if not proposal_path.is_file() or not validation_path.is_file():
        parser.error(
            "the output directory must contain predictor_proposal.json and "
            "research_validation.json"
        )

    proposal = load_research_proposal(
        json.loads(proposal_path.read_text(encoding="utf-8"))
    )
    validation = ResearchValidationResult.model_validate(
        json.loads(validation_path.read_text(encoding="utf-8"))
    )
    print(render_academic_research_summary(proposal, validation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
