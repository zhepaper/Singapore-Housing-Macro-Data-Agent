from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHECKPOINT_ORDER = ("retrieved", "normalized", "transformed", "validated", "reported")


@dataclass(frozen=True)
class RunPaths:
    root: str
    raw: str
    normalized: str
    metrics: str
    report: str
    checkpoints: str
    manifest: str
    validation_report: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def generate_run_id(now: datetime | None = None) -> str:
    timestamp = now or datetime.now(timezone.utc)
    return timestamp.strftime("%Y%m%dT%H%M%S%fZ")


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def initialize_run(
    *,
    project_root: Path,
    reporting_as_of_date: str,
    catalog_version: str,
    prompt_version: str,
    run_id: str | None = None,
) -> tuple[str, RunPaths, dict[str, Any]]:
    selected_run_id = run_id or generate_run_id()
    run_root = project_root / "runs" / selected_run_id
    if run_root.exists():
        raise FileExistsError(f"Run directory already exists: {run_root}")

    directories = {
        "raw": run_root / "raw",
        "normalized": run_root / "normalized",
        "metrics": run_root / "metrics",
        "report": run_root / "report",
        "checkpoints": run_root / "checkpoints",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=False)

    paths = RunPaths(
        root=str(run_root),
        raw=str(directories["raw"]),
        normalized=str(directories["normalized"]),
        metrics=str(directories["metrics"]),
        report=str(directories["report"]),
        checkpoints=str(directories["checkpoints"]),
        manifest=str(run_root / "run_manifest.json"),
        validation_report=str(run_root / "validation_report.json"),
    )
    started_at = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "run_id": selected_run_id,
        "reporting_as_of_date": reporting_as_of_date,
        "catalog_version": catalog_version,
        "prompt_version": prompt_version,
        "started_at": started_at,
        "completed_at": None,
        "status": "running",
        "sources": [],
        "artifacts": {
            key: str(Path(value).relative_to(project_root))
            for key, value in paths.to_dict().items()
        },
        "validation_errors": [],
        "warnings": [],
        "counts": {},
    }
    _atomic_json_write(Path(paths.manifest), manifest)
    return selected_run_id, paths, manifest


def load_run(project_root: Path, run_id: str) -> tuple[RunPaths, dict[str, Any]]:
    run_root = project_root / "runs" / run_id
    manifest_path = run_root / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Run manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = {
        key: str(project_root / value) if not Path(value).is_absolute() else value
        for key, value in manifest["artifacts"].items()
    }
    paths = RunPaths(**artifacts)
    return paths, manifest


def save_checkpoint(paths: RunPaths, stage: str, state: dict[str, Any]) -> str:
    safe_stage = "_".join(part for part in stage.lower().split() if part)
    if not safe_stage or not safe_stage.replace("_", "").isalnum():
        raise ValueError(f"Invalid checkpoint stage: {stage!r}")
    checkpoint_path = Path(paths.checkpoints) / f"{safe_stage}.json"
    if checkpoint_path.exists():
        raise FileExistsError(f"Checkpoint already exists: {checkpoint_path}")
    _atomic_json_write(checkpoint_path, state)
    return str(checkpoint_path)


def load_latest_checkpoint(paths: RunPaths) -> tuple[str, dict[str, Any]]:
    checkpoint_dir = Path(paths.checkpoints)
    for stage in reversed(CHECKPOINT_ORDER):
        path = checkpoint_dir / f"{stage}.json"
        if path.is_file():
            return stage, json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"No resumable checkpoint found in {checkpoint_dir}")


def finalize_manifest(
    paths: RunPaths,
    *,
    status: str,
    sources: list[dict[str, Any]],
    validation_errors: list[str],
    counts: dict[str, int],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    if status not in {"complete", "partial", "failed"}:
        raise ValueError(f"Invalid terminal status: {status!r}")
    manifest_path = Path(paths.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["status"] != "running":
        raise ValueError(f"Run is already terminal: {manifest['status']}")
    project_root = Path(paths.root).resolve().parents[1]

    def portable(value: str | None) -> str | None:
        if not value:
            return value
        path = Path(value)
        if not path.is_absolute():
            return value
        try:
            return str(path.resolve().relative_to(project_root))
        except ValueError:
            return value

    portable_sources = []
    for source in sources:
        item = dict(source)
        item["raw_snapshot_path"] = portable(item.get("raw_snapshot_path"))
        item["raw_page_paths"] = [portable(path) for path in item.get("raw_page_paths", [])]
        portable_sources.append(item)
    manifest.update({
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "sources": portable_sources,
        "validation_errors": validation_errors,
        "counts": counts,
        "warnings": warnings or [],
    })
    _atomic_json_write(manifest_path, manifest)
    _atomic_json_write(Path(paths.validation_report), {
        "run_id": manifest["run_id"],
        "status": "pass" if not validation_errors else "fail",
        "errors": validation_errors,
    })
    return manifest
