from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypedDict

from housing_agent.onboarding.mapping_models import (
    AdaptiveMappingResult,
    UnifiedDataPlanReviewResult,
    UnifiedDataPlanReviewSubmission,
)
from housing_agent.onboarding.models import ApprovedCatalogEntry, load_approved_catalog_entry
from housing_agent.preparation.models import PreparationContract, RawSnapshotEvidence
from housing_agent.processing.integrity import verify_frozen_data_plan
from housing_agent.processing.models import FrozenDataPlan, FrozenSeriesPlan


def build_unified_review_markdown(
    *,
    approved_sources: list[ApprovedCatalogEntry],
    snapshots: list[RawSnapshotEvidence],
    mapping_results: list[AdaptiveMappingResult],
    preparation_contracts: list[PreparationContract],
) -> str:
    snapshot_by_id = {item.source_id: item for item in snapshots}
    mapping_by_id = {item.source_id: item for item in mapping_results}
    preparation_by_id = {item.source_id: item for item in preparation_contracts}
    lines = [
        "# Unified Data Plan Review",
        "",
        "| Source | Raw snapshot | Mapping | Coverage | Unit | Native / update frequency | Approved transformation proposal |",
        "|---|---|---|---|---|---|---|",
    ]
    for approved in sorted(approved_sources, key=lambda item: item.entry.source_id):
        entry = approved.entry
        snapshot = snapshot_by_id.get(entry.source_id)
        mapping = mapping_by_id.get(entry.source_id)
        preparation = preparation_by_id.get(entry.source_id)
        execution = mapping.accepted_execution if mapping else None
        contract = mapping.accepted_proposal.mapping_contract if mapping and mapping.accepted_proposal else None
        mapping_text = (
            f"{contract.layout}: {contract.date_field or contract.wide_period_pattern} → {contract.value_field or 'period values'}"
            if contract else "not ready"
        )
        coverage = (
            f"{execution.observed_period_start}–{execution.observed_period_end}; "
            f"{execution.non_null_observation_count} non-null"
            if execution else "not validated"
        )
        transformation = "not ready"
        if preparation:
            quarterly = (
                preparation.quarterly_comparison.aggregation_method.value
                if preparation.quarterly_comparison else "native only"
            )
            changes = ", ".join(item.method.value for item in preparation.change_calculations)
            transformation = f"quarterly={quarterly}; changes={changes}"
        snapshot_text = (
            f"saved `{snapshot.sha256[:12]}…`" if snapshot and snapshot.sha256 else "failed"
        )
        lines.append(
            "| " + " | ".join([
                entry.source_id,
                snapshot_text,
                mapping_text,
                coverage,
                entry.unit,
                f"{entry.native_frequency} / {entry.update_frequency}",
                transformation,
            ]) + " |"
        )
    lines.extend([
        "",
        "Choose one decision for every source: approve, request mapping revision, replace source, or reject.",
        "The plan is frozen only after explicit confirmation. Approving does not allow the system to alter definitions, mappings, or transformations afterward.",
    ])
    return "\n".join(lines) + "\n"


def evaluate_and_freeze_data_plan(
    *,
    approved_sources: list[ApprovedCatalogEntry],
    snapshots: list[RawSnapshotEvidence],
    mapping_results: list[AdaptiveMappingResult],
    preparation_contracts: list[PreparationContract],
    submission: UnifiedDataPlanReviewSubmission,
    output_directory: str | Path | None = None,
) -> tuple[UnifiedDataPlanReviewResult, FrozenDataPlan | None]:
    reviewed_at = datetime.now(timezone.utc)
    errors: list[str] = []
    warnings: list[str] = []
    if submission.confirmation_status != "confirmed":
        errors.append("Unified review remains a draft until explicitly confirmed.")
    source_by_id = {item.entry.source_id: item for item in approved_sources}
    snapshot_by_id = {item.source_id: item for item in snapshots}
    mapping_by_id = {item.source_id: item for item in mapping_results}
    preparation_by_id = {item.source_id: item for item in preparation_contracts}
    expected = set(source_by_id)
    submitted = {item.source_id for item in submission.source_decisions}
    if missing := expected - submitted:
        errors.append(f"Unified review is missing sources: {sorted(missing)}")
    if unknown := submitted - expected:
        errors.append(f"Unified review contains unknown sources: {sorted(unknown)}")

    approved_ids: list[str] = []
    revision_ids: list[str] = []
    replacement_ids: list[str] = []
    rejected_ids: list[str] = []
    frozen_series: list[FrozenSeriesPlan] = []
    for decision in submission.source_decisions:
        if decision.decision == "request_mapping_revision":
            revision_ids.append(decision.source_id)
            continue
        if decision.decision == "replace_source":
            replacement_ids.append(decision.source_id)
            continue
        if decision.decision == "reject":
            rejected_ids.append(decision.source_id)
            continue
        approved_ids.append(decision.source_id)
        approved = source_by_id.get(decision.source_id)
        snapshot = snapshot_by_id.get(decision.source_id)
        mapping = mapping_by_id.get(decision.source_id)
        preparation = preparation_by_id.get(decision.source_id)
        role = decision.role_assignment
        if approved is None or snapshot is None or mapping is None or preparation is None or role is None:
            errors.append(f"{decision.source_id}: source, snapshot, mapping, preparation, or role is missing.")
            continue
        if snapshot.status != "pass" or not snapshot.snapshot_path or not snapshot.sha256:
            errors.append(f"{decision.source_id}: preserved raw snapshot did not pass.")
            continue
        if (
            mapping.status != "ready_for_human_review"
            or mapping.accepted_proposal is None
            or mapping.accepted_execution is None
            or mapping.accepted_execution.status != "pass"
        ):
            errors.append(f"{decision.source_id}: mapping has not passed full-snapshot validation.")
            continue
        if role.source_id != decision.source_id:
            errors.append(f"{decision.source_id}: role assignment has a different source_id.")
            continue
        if mapping.series_id != role.series_id:
            errors.append(f"{decision.source_id}: role series_id differs from the validated mapping.")
            continue
        if preparation.source_id != decision.source_id:
            errors.append(f"{decision.source_id}: preparation contract has a different source_id.")
            continue
        entry = approved.entry
        frozen_series.append(FrozenSeriesPlan(
            source_id=decision.source_id,
            series_id=role.series_id,
            series_label=role.series_label,
            snapshot_path=snapshot.snapshot_path,
            snapshot_sha256=snapshot.sha256,
            mapping_contract=mapping.accepted_proposal.mapping_contract,
            preparation_contract=preparation,
            definition=entry.definition,
            unit=entry.unit,
            observation_frequency=entry.native_frequency,
            update_frequency=entry.update_frequency,
            series_type=entry.series_type,
            portfolio_role=role.portfolio_role,
            market_role=role.market_role,
            release_lag_days=role.release_lag_days,
            minimum_observations=role.minimum_observations,
            max_staleness_periods=role.max_staleness_periods,
            duplicate_policy=role.duplicate_policy,
        ))

    frozen: FrozenDataPlan | None = None
    frozen_path: str | None = None
    if not errors and not revision_ids and not replacement_ids and not rejected_ids:
        try:
            threshold = Decimal(submission.feature_redundancy_threshold)
        except InvalidOperation:
            errors.append("feature_redundancy_threshold is not a valid decimal.")
        else:
            draft = FrozenDataPlan(
                plan_id=submission.plan_id,
                plan_version=submission.plan_version,
                plan_sha256="0" * 64,
                approval_status="approved",
                approved_by=submission.reviewer,
                approved_at=reviewed_at,
                reporting_as_of_date=submission.reporting_as_of_date,
                historical_start_date=submission.historical_start_date,
                historical_end_date=submission.historical_end_date,
                minimum_quarterly_observations=submission.minimum_quarterly_observations,
                feature_redundancy_threshold=threshold,
                series=tuple(frozen_series),
            )
            frozen = draft.model_copy(update={"plan_sha256": draft.computed_sha256()})
            verification = verify_frozen_data_plan(frozen)
            if verification.status != "pass":
                errors.extend(item.message for item in verification.issues)
                frozen = None
            elif output_directory is not None:
                path = Path(output_directory) / "frozen_data_plan.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(frozen.model_dump_json(indent=2) + "\n", encoding="utf-8")
                frozen_path = str(path.resolve())

    if errors:
        status = "invalid"
    elif revision_ids:
        status = "needs_mapping_revision"
    elif replacement_ids:
        status = "replace_source"
    elif rejected_ids:
        status = "rejected"
    else:
        status = "approved"
    result = UnifiedDataPlanReviewResult(
        status=status,
        reviewer=submission.reviewer,
        reviewed_at=reviewed_at,
        approved_source_ids=approved_ids if status == "approved" else [],
        revision_source_ids=revision_ids,
        replacement_source_ids=replacement_ids,
        rejected_source_ids=rejected_ids,
        frozen_plan_path=frozen_path,
        errors=errors,
        warnings=warnings,
    )
    return result, frozen


class UnifiedPlanReviewState(TypedDict, total=False):
    approved_catalog_entries: list[dict[str, Any]]
    raw_snapshot_evidence: list[dict[str, Any]]
    adaptive_mapping_results: list[dict[str, Any]]
    approved_preparation_contracts: list[dict[str, Any]]
    unified_review_submission: dict[str, Any]
    unified_review_artifact_dir: str
    unified_review_markdown: str
    unified_review_result: dict[str, Any]
    frozen_data_plan: dict[str, Any]


def unified_plan_review_node(state: UnifiedPlanReviewState) -> UnifiedPlanReviewState:
    sources = [load_approved_catalog_entry(item) for item in state["approved_catalog_entries"]]
    snapshots = [RawSnapshotEvidence.model_validate(item) for item in state["raw_snapshot_evidence"]]
    mappings = [AdaptiveMappingResult.model_validate(item) for item in state["adaptive_mapping_results"]]
    preparations = [PreparationContract.model_validate(item) for item in state["approved_preparation_contracts"]]
    submission = UnifiedDataPlanReviewSubmission.model_validate(state["unified_review_submission"])
    artifact_dir = state.get("unified_review_artifact_dir")
    markdown = build_unified_review_markdown(
        approved_sources=sources,
        snapshots=snapshots,
        mapping_results=mappings,
        preparation_contracts=preparations,
    )
    result, frozen = evaluate_and_freeze_data_plan(
        approved_sources=sources,
        snapshots=snapshots,
        mapping_results=mappings,
        preparation_contracts=preparations,
        submission=submission,
        output_directory=artifact_dir,
    )
    output = {
        "unified_review_markdown": markdown,
        "unified_review_result": result.model_dump(mode="json"),
        "frozen_data_plan": frozen.model_dump(mode="json") if frozen else {},
    }
    if artifact_dir:
        root = Path(artifact_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "unified_review.md").write_text(markdown, encoding="utf-8")
        (root / "unified_review_submission.json").write_text(
            submission.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (root / "unified_review_result.json").write_text(
            result.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    return output
