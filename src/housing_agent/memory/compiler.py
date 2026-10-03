from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from housing_agent.memory.models import (
    AnalyticalPreferences,
    ApprovedPredictorMemory,
    ApprovedPreparationMemory,
    DataPreferences,
    DecisionEvent,
    MemoryManifest,
    MemorySnapshot,
    PendingQuestion,
    ReportingPreferences,
    ResearchPreferences,
)
from housing_agent.memory.store import DecisionLogStore
from housing_agent.research.models import ApprovedResearchScope


def _latest_confirmed_payload(
    events: list[DecisionEvent], decision_type: str
) -> dict[str, Any] | None:
    matches = [
        event for event in events
        if event.status == "confirmed" and event.decision_type == decision_type
    ]
    return matches[-1].payload if matches else None


def _active_pending_questions(events: list[DecisionEvent]) -> list[PendingQuestion]:
    superseded = {event.supersedes for event in events if event.supersedes}
    return [
        PendingQuestion.model_validate(event.payload)
        for event in events
        if event.decision_type == "pending_question"
        and event.status == "pending"
        and event.event_id not in superseded
    ]


def compile_memory(
    events: list[DecisionEvent], *, compiled_at: datetime | None = None
) -> tuple[MemorySnapshot, MemoryManifest]:
    if not events:
        raise ValueError("cannot compile memory from an empty decision log")
    project_ids = {event.project_id for event in events}
    if len(project_ids) != 1:
        raise ValueError("memory events must belong to exactly one project")
    required = (
        "scope",
        "research_preferences",
        "data_preferences",
        "analytical_preferences",
        "reporting_preferences",
    )
    payloads = {name: _latest_confirmed_payload(events, name) for name in required}
    missing = [name for name, value in payloads.items() if value is None]
    if missing:
        raise ValueError(f"confirmed memory decisions are missing: {missing}")

    predictor_payload = _latest_confirmed_payload(events, "predictor_approval")
    predictors = (
        [ApprovedPredictorMemory.model_validate(item) for item in predictor_payload["predictors"]]
        if predictor_payload else []
    )
    preparation_by_source: dict[str, ApprovedPreparationMemory] = {}
    for event in events:
        if event.status != "confirmed" or event.decision_type != "preparation_approval":
            continue
        for item in event.payload.get("contracts", []):
            parsed = ApprovedPreparationMemory.model_validate(item)
            preparation_by_source[parsed.source_id] = parsed
    timestamp = compiled_at or max(event.recorded_at for event in events)
    snapshot = MemorySnapshot(
        project_id=next(iter(project_ids)),
        memory_version=max(event.sequence for event in events),
        compiled_at=timestamp,
        approved_scope=ApprovedResearchScope.model_validate(payloads["scope"]),
        research_preferences=ResearchPreferences.model_validate(payloads["research_preferences"]),
        data_preferences=DataPreferences.model_validate(payloads["data_preferences"]),
        analytical_preferences=AnalyticalPreferences.model_validate(payloads["analytical_preferences"]),
        reporting_preferences=ReportingPreferences.model_validate(payloads["reporting_preferences"]),
        approved_predictors=predictors,
        approved_preparation_plans=list(preparation_by_source.values()),
        pending_questions=_active_pending_questions(events),
        source_event_ids=[event.event_id for event in events],
    )
    manifest = MemoryManifest(
        project_id=snapshot.project_id,
        memory_version=snapshot.memory_version,
        snapshot_sha256=memory_snapshot_sha256(snapshot),
        snapshot_path=None,
        event_count=len(events),
        compiled_at=timestamp,
    )
    return snapshot, manifest


def memory_snapshot_sha256(snapshot: MemorySnapshot) -> str:
    canonical = json.dumps(
        snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def persist_memory_snapshot(
    snapshot: MemorySnapshot, manifest: MemoryManifest, directory: Path
) -> MemoryManifest:
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_path = directory / f"memory_v{snapshot.memory_version}.json"
    snapshot_path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    persisted_manifest = manifest.model_copy(
        update={"snapshot_path": str(snapshot_path.resolve())}
    )
    (directory / "memory_manifest.json").write_text(
        json.dumps(persisted_manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return persisted_manifest


class MemoryCompilerState(TypedDict, total=False):
    memory_decision_log_path: str
    memory_artifact_dir: str
    memory_snapshot: dict[str, Any]
    memory_manifest: dict[str, Any]


def memory_compiler_node(state: MemoryCompilerState) -> MemoryCompilerState:
    events = DecisionLogStore(Path(state["memory_decision_log_path"])).load()
    snapshot, manifest = compile_memory(events)
    if state.get("memory_artifact_dir"):
        manifest = persist_memory_snapshot(
            snapshot, manifest, Path(state["memory_artifact_dir"])
        )
    return {
        "memory_snapshot": snapshot.model_dump(mode="json"),
        "memory_manifest": manifest.model_dump(mode="json"),
    }
