#!/usr/bin/env python3
"""Compile an append-only project decision log into a versioned memory snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.memory.compiler import memory_compiler_node  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--decision-log",
        type=Path,
        default=PROJECT_ROOT / "config/project_memory.seed.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs/project_memory",
    )
    args = parser.parse_args()
    result = memory_compiler_node({
        "memory_decision_log_path": str(args.decision_log),
        "memory_artifact_dir": str(args.output),
    })
    snapshot = result["memory_snapshot"]
    manifest = result["memory_manifest"]
    print(f"Project memory: {snapshot['project_id']}")
    print(f"Memory version: {snapshot['memory_version']}")
    print(f"Approved predictors: {len(snapshot['approved_predictors'])}")
    print(f"Pending questions: {len(snapshot['pending_questions'])}")
    print(f"Snapshot SHA-256: {manifest['snapshot_sha256']}")
    print(f"Memory artifacts: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
