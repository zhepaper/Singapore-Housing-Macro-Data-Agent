#!/usr/bin/env python3
"""Package a completed run as portable, reviewable repository artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def rewrite_run_path(value: str | None, run_id: str) -> str | None:
    if value is None:
        return None
    prefix = f"runs/{run_id}/"
    if value == f"runs/{run_id}":
        return "sample_run"
    return f"sample_run/{value.removeprefix(prefix)}" if value.startswith(prefix) else value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--destination", type=Path, default=PROJECT_ROOT / "sample_run")
    args = parser.parse_args()

    source = PROJECT_ROOT / "runs" / args.run_id
    manifest_path = source / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError("Only a complete run may be packaged as the reference sample")

    destination = args.destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")
    destination.mkdir(parents=True)
    for directory in ("raw", "normalized", "metrics", "report"):
        shutil.copytree(source / directory, destination / directory)
    shutil.copy2(source / "validation_report.json", destination / "validation_report.json")

    manifest["artifacts"] = {
        key: rewrite_run_path(value, args.run_id)
        for key, value in manifest["artifacts"].items()
        if key != "checkpoints"
    }
    for source_item in manifest["sources"]:
        source_item["raw_snapshot_path"] = rewrite_run_path(
            source_item.get("raw_snapshot_path"), args.run_id
        )
        source_item["raw_page_paths"] = [
            rewrite_run_path(path, args.run_id) for path in source_item.get("raw_page_paths", [])
        ]
    (destination / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    evidence_path = destination / "metrics/evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    for item in evidence.values():
        item["raw_snapshot_path"] = rewrite_run_path(
            item.get("raw_snapshot_path"), args.run_id
        )
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
