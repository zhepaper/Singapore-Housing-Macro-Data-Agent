from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, TypedDict

from housing_agent.memory.compiler import memory_snapshot_sha256
from housing_agent.memory.models import MemoryManifest, MemorySnapshot
from housing_agent.onboarding.models import (
    ApprovedCatalogEntry,
    load_approved_catalog_entry,
)
from housing_agent.preparation.models import (
    DataPreparationProposal,
    PreparationReviewView,
    PreparationValidation,
    RawSnapshotEvidence,
)
from housing_agent.preparation.presentation import build_preparation_review_view
from housing_agent.preparation.raw_capture import capture_raw_snapshot
from housing_agent.preparation.validation import validate_preparation_proposal
from housing_agent.research.providers import provider_spec


PREPARATION_ADVISOR_VERSION = "data-preparation-advisor-v2-raw-first"

PREPARATION_ADVISOR_INSTRUCTIONS = """You are the data-preparation advisory component of an auditable Singapore housing research workflow.

You receive confirmed project memory, human-approved source profiles, and evidence from newly saved raw-data snapshots. Recommend explicit analytical operations for human review.

BOUNDARIES
- Preserve every native series. A quarterly comparison is an additional derived view.
- Never interpolate annual data, convert missing values to zero, invent observations, or change source definitions.
- Recommend a quarterly comparison only for monthly input. Choose exactly one of last, mean, or sum and explain the economic meaning. Do not claim one method is universally correct.
- Stock and index levels must not be summed. Rates must not be summed.
- Rate changes use absolute, percentage-point, basis-point, or a published-change representation. Index and level changes use absolute or percentage changes.
- Use correct calendar lags: monthly MoM=1, QoQ=3, YoY=12; quarterly QoQ=1 and YoY=4; annual YoY=1.
- Predictive alignment is optional, exploratory, and non-causal. Annual structural context cannot receive a quarterly predictive lag.
- Use confirmed predictor-selection rationale and reporting preferences from memory. Pending questions are not approvals.
- decision_basis must include at least one `memory_event:<event_id>` reference and one `source_profile:<source_id>` reference.
- Return one recommendation for every approved source and no recommendation for any other source.
- concise_recommendation is the short, human-facing advice shown immediately below the
  data inventory table. It must state the common comparison frequency, the most important
  series-specific treatments, and any essential caveat in no more than 150 words.
- Describe target-series history only from observed_period_start, observed_period_end, and
  coverage_profile_scope. Never infer target-series coverage from table columns or the
  histories of other rows.
- Distinguish source availability from analytical eligibility: observations after the
  confirmed reporting_as_of_date must be excluded by the later deterministic as-of gate.
- Return only schema-valid English JSON. All numeric calculations remain deterministic and occur after human approval.

EXACT ENUM VALUES
- missing_value_policy must be exactly `preserve_null`.
- predictive_alignment.interpretation must be exactly `exploratory_predictive_alignment`.
- preserve_native_view must be true and interpolation_allowed must be false.
"""


class PreparationAdvisorClient(Protocol):
    def advise(
        self, *, instructions: str, input_text: str, model: str
    ) -> tuple[DataPreparationProposal, dict[str, Any], dict[str, Any]]: ...


class PreparationStructuredOutputError(ValueError):
    def __init__(self, message: str, *, raw: dict[str, Any], metadata: dict[str, Any]):
        super().__init__(message)
        self.raw = raw
        self.metadata = metadata


class GeminiPreparationAdvisorClient:
    def __init__(self, *, api_key: str | None = None) -> None:
        from google import genai

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is required for the preparation advisor.")
        self._client = genai.Client(api_key=key)

    def advise(self, *, instructions: str, input_text: str, model: str):
        interaction = self._client.interactions.create(
            model=model,
            system_instruction=instructions,
            input=input_text,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": DataPreparationProposal.model_json_schema(),
            },
            store=False,
        )
        if not interaction.output_text:
            raise RuntimeError("Gemini returned no preparation-advisor output.")
        raw = interaction.model_dump(mode="json")
        metadata = {
            "provider": "gemini",
            "model": raw.get("model", model),
            "interaction_id": raw.get("id"),
            "usage": raw.get("usage") or {},
        }
        try:
            proposal = DataPreparationProposal.model_validate_json(
                interaction.output_text
            )
            repaired = False
        except Exception as first_error:
            try:
                from json_repair import repair_json

                proposal = DataPreparationProposal.model_validate(
                    repair_json(interaction.output_text, return_objects=True)
                )
                repaired = True
            except Exception as repair_error:
                raise PreparationStructuredOutputError(
                    f"Schema validation failed: {repair_error}",
                    raw=raw,
                    metadata=metadata,
                ) from first_error
        metadata["structured_output_repaired"] = repaired
        return proposal, raw, metadata


def build_preparation_input(
    memory: MemorySnapshot,
    manifest: MemoryManifest,
    approved_sources: list[ApprovedCatalogEntry],
    raw_snapshots: list[RawSnapshotEvidence],
    mapping_executions: list[MappingExecutionReport] | None = None,
) -> str:
    mapping_by_id = {
        item.source_id: item for item in (mapping_executions or [])
    }
    source_profiles = []
    for approved in approved_sources:
        entry = approved.entry
        mapped = mapping_by_id.get(entry.source_id)
        source_profiles.append({
            "catalog_version": approved.catalog_version,
            "approved_by": approved.approved_by,
            "source_id": entry.source_id,
            "predictor_id": entry.predictor_id,
            "official_agency": entry.official_agency,
            "dataset_title": entry.dataset_title,
            "dataset_id": entry.dataset_id,
            "table_id": entry.table_id,
            "definition": entry.definition,
            "unit": entry.unit,
            "native_frequency": entry.native_frequency,
            "update_frequency": entry.update_frequency,
            "series_type": entry.series_type.value,
            "series_identifier": entry.series_identifier,
            "exact_series_label": entry.exact_series_label,
            "point_in_time_notes": entry.point_in_time_notes,
            "limitations": entry.limitations,
            "probe_status": entry.probe.status,
            "observed_period_start": (
                mapped.observed_period_start if mapped else entry.probe.observed_period_start
            ),
            "observed_period_end": (
                mapped.observed_period_end if mapped else entry.probe.observed_period_end
            ),
            "non_null_observation_count": (
                mapped.non_null_observation_count if mapped else entry.probe.non_null_observation_count
            ),
            "missing_observation_count": (
                mapped.missing_observation_count if mapped else entry.probe.missing_observation_count
            ),
            "missing_observation_definition": (
                "Calendar periods without a value between observed_period_start and "
                "observed_period_end; leading table periods before series inception are excluded."
            ),
            "coverage_profile_scope": (
                "full_preserved_snapshot" if mapped else entry.probe.coverage_profile_scope
            ),
        })
    return "\n\n".join([
        "CONFIRMED PROJECT MEMORY\n"
        + json.dumps(memory.model_dump(mode="json"), indent=2, sort_keys=True),
        "MEMORY MANIFEST\n"
        + json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        "HUMAN-APPROVED VERIFIED SOURCE PROFILES\n"
        + json.dumps(source_profiles, indent=2, sort_keys=True),
        "NEWLY SAVED RAW-DATA SNAPSHOT EVIDENCE\n"
        + json.dumps(
            [item.model_dump(mode="json") for item in raw_snapshots],
            indent=2,
            sort_keys=True,
        ),
        "DETERMINISTIC FULL-SNAPSHOT MAPPING EXECUTION\n"
        + json.dumps(
            [item.model_dump(mode="json") for item in (mapping_executions or [])],
            indent=2,
            sort_keys=True,
        ),
        "Recommend reviewable preparation contracts. Do not calculate or alter observations.",
    ])


class DataPreparationAdvisorState(TypedDict, total=False):
    memory_snapshot: dict[str, Any]
    memory_manifest: dict[str, Any]
    approved_catalog_entries: list[dict[str, Any]]
    preparation_provider: str
    preparation_model: str | None
    max_preparation_attempts: int
    preparation_artifact_dir: str
    raw_snapshot_evidence: list[dict[str, Any]]
    mapping_execution_reports: list[dict[str, Any]]
    preparation_proposal: dict[str, Any]
    preparation_validation: dict[str, Any]
    preparation_metadata: dict[str, Any]
    preparation_raw_response: dict[str, Any]
    preparation_errors: list[str]
    preparation_review_view: dict[str, Any]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_data_preparation_advisor_node(
    client_factory: Callable[[], PreparationAdvisorClient] | None = None,
    snapshot_capture: Callable[[ApprovedCatalogEntry, Path], RawSnapshotEvidence] | None = None,
):
    def node(state: DataPreparationAdvisorState) -> DataPreparationAdvisorState:
        started_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []
        proposal: DataPreparationProposal | None = None
        validation: PreparationValidation | None = None
        raw: dict[str, Any] = {}
        provider_metadata: dict[str, Any] = {}
        snapshots: list[RawSnapshotEvidence] = []
        review_view: PreparationReviewView | None = None
        try:
            memory = MemorySnapshot.model_validate(state["memory_snapshot"])
            manifest = MemoryManifest.model_validate(state["memory_manifest"])
            if manifest.project_id != memory.project_id or (
                manifest.memory_version != memory.memory_version
            ):
                raise ValueError("Memory manifest does not identify this snapshot")
            if manifest.snapshot_sha256 != memory_snapshot_sha256(memory):
                raise ValueError("Memory snapshot checksum does not match manifest")
            approved_sources = [
                load_approved_catalog_entry(item)
                for item in state["approved_catalog_entries"]
            ]
            if not approved_sources:
                raise ValueError("At least one human-approved source profile is required")
            source_ids = [item.entry.source_id for item in approved_sources]
            if len(source_ids) != len(set(source_ids)):
                raise ValueError("Approved source profiles contain duplicate source IDs")
            if state.get("raw_snapshot_evidence"):
                snapshots = [
                    RawSnapshotEvidence.model_validate(item)
                    for item in state["raw_snapshot_evidence"]
                ]
            else:
                if not state.get("preparation_artifact_dir"):
                    raise ValueError(
                        "preparation_artifact_dir is required to preserve raw snapshots"
                    )
                snapshot_directory = Path(state["preparation_artifact_dir"]) / "raw"
                capture = snapshot_capture or (
                    lambda approved, directory: capture_raw_snapshot(
                        approved, snapshot_directory=directory
                    )
                )
                snapshots = [capture(item, snapshot_directory) for item in approved_sources]
            snapshot_ids = [item.source_id for item in snapshots]
            if set(snapshot_ids) != set(source_ids) or len(snapshot_ids) != len(set(snapshot_ids)):
                raise ValueError("Raw snapshot evidence must cover every approved source exactly once")
            failed_snapshots = [item for item in snapshots if item.status != "pass"]
            if failed_snapshots:
                details = {
                    item.source_id: item.errors for item in failed_snapshots
                }
                raise ValueError(f"Raw snapshot capture failed: {details}")
            from housing_agent.onboarding.mapping_models import MappingExecutionReport

            mapping_executions = [
                MappingExecutionReport.model_validate(item)
                for item in state.get("mapping_execution_reports", [])
            ]
            if mapping_executions:
                mapped_ids = {item.source_id for item in mapping_executions}
                if mapped_ids != set(source_ids) or any(
                    item.status != "pass" for item in mapping_executions
                ):
                    raise ValueError(
                        "Mapping execution reports must pass and cover every approved source exactly once"
                    )
            provider = state.get("preparation_provider", "gemini")
            if provider != "gemini":
                raise ValueError("DataPreparationAdvisorNode v1 supports provider='gemini'")
            model = state.get("preparation_model") or provider_spec("gemini").default_model
            client = client_factory() if client_factory else GeminiPreparationAdvisorClient()
            maximum_attempts = state.get("max_preparation_attempts", 2)
            if not isinstance(maximum_attempts, int) or not 1 <= maximum_attempts <= 3:
                raise ValueError("max_preparation_attempts must be an integer from 1 to 3")
            base_input = build_preparation_input(
                memory, manifest, approved_sources, snapshots, mapping_executions
            )
            feedback = ""
            raw_attempts: list[dict[str, Any]] = []
            for attempt in range(1, maximum_attempts + 1):
                try:
                    proposal, attempt_raw, provider_metadata = client.advise(
                        instructions=PREPARATION_ADVISOR_INSTRUCTIONS,
                        input_text=base_input + feedback,
                        model=model,
                    )
                    raw_attempts.append(attempt_raw)
                except PreparationStructuredOutputError as exc:
                    raw_attempts.append(exc.raw)
                    provider_metadata = exc.metadata
                    if attempt == maximum_attempts:
                        raise
                    feedback = (
                        "\n\nPREVIOUS RESPONSE FAILED THE TYPED SCHEMA\n"
                        + str(exc)
                        + "\nReturn a complete replacement JSON object. Use exact enum "
                        "values from the schema and instructions; do not paraphrase them."
                    )
                    continue
                if proposal.memory_sha256 != manifest.snapshot_sha256:
                    raise ValueError("Advisor proposal cites a different memory checksum")
                validation = validate_preparation_proposal(
                    proposal,
                    memory=memory,
                    approved_sources=approved_sources,
                )
                if validation.automated_validation_status == "pass":
                    break
                if attempt < maximum_attempts:
                    feedback = (
                        "\n\nPREVIOUS RESPONSE FAILED DETERMINISTIC VALIDATION\n"
                        + json.dumps(validation.errors, indent=2)
                        + "\nReturn a complete corrected proposal without weakening any rule."
                    )
            raw = {"attempts": raw_attempts}
            provider_metadata["preparation_attempt_count"] = len(raw_attempts)
            if proposal is not None and validation is not None:
                review_view = build_preparation_review_view(
                    proposal, approved_sources, snapshots
                )
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        metadata = {
            "execution_status": "fail" if errors else "success",
            "advisor_version": PREPARATION_ADVISOR_VERSION,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            **provider_metadata,
        }
        validation_dict = validation.model_dump(mode="json") if validation else {
            "automated_validation_status": "not_run",
            "human_review_status": "not_ready",
            "contract_validations": [],
            "errors": errors,
            "warnings": [],
        }
        result: DataPreparationAdvisorState = {
            "preparation_proposal": proposal.model_dump(mode="json") if proposal else {},
            "preparation_validation": validation_dict,
            "preparation_metadata": metadata,
            "preparation_raw_response": raw,
            "preparation_errors": errors,
            "raw_snapshot_evidence": [
                item.model_dump(mode="json") for item in snapshots
            ],
            "preparation_review_view": (
                review_view.model_dump(mode="json") if review_view else {}
            ),
        }
        if state.get("preparation_artifact_dir"):
            directory = Path(state["preparation_artifact_dir"])
            _write_json(directory / "preparation_proposal.json", result["preparation_proposal"])
            _write_json(directory / "preparation_validation.json", validation_dict)
            _write_json(directory / "preparation_metadata.json", metadata)
            _write_json(directory / "preparation_raw_response.json", raw)
            _write_json(directory / "preparation_errors.json", {"errors": errors})
            _write_json(
                directory / "raw_snapshot_evidence.json",
                result["raw_snapshot_evidence"],
            )
            _write_json(
                directory / "preparation_review_view.json",
                result["preparation_review_view"],
            )
            if review_view is not None:
                (directory / "preparation_review.md").write_text(
                    review_view.markdown + "\n", encoding="utf-8"
                )
        return result

    return node


data_preparation_advisor_node = make_data_preparation_advisor_node()


def build_data_preparation_advisor_graph(
    client_factory: Callable[[], PreparationAdvisorClient] | None = None,
    snapshot_capture: Callable[[ApprovedCatalogEntry, Path], RawSnapshotEvidence] | None = None,
):
    """Compile the isolated, review-gated preparation-advisor LangGraph."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(DataPreparationAdvisorState)
    graph.add_node(
        "advise_data_preparation",
        make_data_preparation_advisor_node(client_factory, snapshot_capture),
    )
    graph.add_edge(START, "advise_data_preparation")
    graph.add_edge("advise_data_preparation", END)
    return graph.compile()
