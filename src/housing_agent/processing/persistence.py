from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from housing_agent.processing.models import CanonicalObservation


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(value), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_observations_csv(path: Path, observations: Iterable[CanonicalObservation]) -> None:
    rows = [item.model_dump(mode="json") for item in observations]
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(CanonicalObservation.model_fields)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            })


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_checkpoint(root: Path, name: str, plan_sha256: str, artifacts: Iterable[Path]) -> None:
    write_json(root / "checkpoints" / f"{name}.json", {
        "checkpoint": name,
        "plan_sha256": plan_sha256,
        "artifacts": {
            str(path.relative_to(root)): file_sha256(path)
            for path in sorted(artifacts)
        },
    })
