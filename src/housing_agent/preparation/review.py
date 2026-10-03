from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from housing_agent.memory.models import DecisionEvent
from housing_agent.memory.store import DecisionLogStore
from housing_agent.onboarding.models import load_approved_catalog_entry
from housing_agent.preparation.models import (
    DataPreparationProposal,
    PreparationReviewResult,
    PreparationReviewSubmission,
    PreparationValidation,
)
from housing_agent.preparation.validation import validate_preparation_contract


class PreparationReviewState(TypedDict, total=False):
    preparation_proposal: dict[str, Any]
    preparation_validation: dict[str, Any]
    approved_catalog_entries: list[dict[str, Any]]
    preparation_review_submission: dict[str, Any]
    preparation_review_artifact_dir: str
    memory_decision_log_path: str
    preparation_review_result: dict[str, Any]
    approved_preparation_contracts: list[dict[str, Any]]
    preparation_memory_event: dict[str, Any]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate_preparation_review(
    *,
    proposal: DataPreparationProposal,
    validation: PreparationValidation,
    approved_catalog_entries: list[dict[str, Any]],
    submission: PreparationReviewSubmission,
) -> PreparationReviewResult:
    errors: list[str] = []
    warnings: list[str] = []
    if submission.confirmation_status != "confirmed":
        errors.append(
            "Review remains a draft until the user confirms the selected option and instructions"
        )
    if validation.automated_validation_status != "pass":
        errors.append("Preparation advice must pass automated validation before review")
    source_profiles = {
        item.entry.source_id: item
        for item in map(load_approved_catalog_entry, approved_catalog_entries)
    }
    expected = {item.contract.source_id for item in proposal.recommendations}
    submitted = {item.source_id for item in submission.source_reviews}
    if missing := expected - submitted:
        errors.append(f"Preparation review is missing sources: {sorted(missing)}")
    if unknown := submitted - expected:
        errors.append(f"Preparation review contains unknown sources: {sorted(unknown)}")
    proposed_contracts = {
        item.contract.source_id: item.contract for item in proposal.recommendations
    }

    approved = []
    rejected: list[str] = []
    revision: list[str] = []
    for item in submission.source_reviews:
        if item.source_id not in expected:
            continue
        if item.decision == "approve":
            assert item.approved_contract is not None
            if item.approved_contract.source_id != item.source_id:
                errors.append(f"{item.source_id}: approved contract has a different source_id")
                continue
            profile = source_profiles.get(item.source_id)
            if profile is None:
                errors.append(f"{item.source_id}: approved source profile is unavailable")
                continue
            contract_validation = validate_preparation_contract(
                item.approved_contract, profile
            )
            if (
                submission.review_choice == "approve_all"
                and item.approved_contract != proposed_contracts[item.source_id]
            ):
                errors.append(
                    f"{item.source_id}: approve_all cannot contain a modified contract"
                )
            if contract_validation.status == "fail":
                errors.extend(
                    f"{item.source_id}: {message}"
                    for message in contract_validation.errors
                )
            else:
                approved.append(item.approved_contract)
                warnings.extend(contract_validation.warnings)
        elif item.decision == "reject":
            rejected.append(item.source_id)
        else:
            revision.append(item.source_id)

    if submission.review_choice == "approve_all" and (
        rejected or revision or len(approved) != len(expected)
    ):
        errors.append("approve_all requires approval of every proposed contract")
    if submission.review_choice == "replace_sources":
        revision = sorted(expected)
        approved = []
        warnings.append("Source replacement returns the workflow to data discovery.")
    if submission.review_choice == "reject_proposal":
        rejected = sorted(expected)
        revision = []
        approved = []

    if errors:
        status = "invalid"
        approved = []
    elif revision:
        status = "needs_revision"
        approved = []
    elif approved:
        status = "approved"
    else:
        status = "rejected"
    return PreparationReviewResult(
        review_status=status,
        plan_version=submission.plan_version,
        reviewer=submission.reviewer,
        reviewed_at=datetime.now(timezone.utc),
        review_choice=submission.review_choice,
        custom_instructions=submission.custom_instructions,
        approved_contracts=approved,
        rejected_source_ids=rejected,
        revision_requested_source_ids=revision,
        errors=errors,
        warnings=warnings,
    )


def append_preparation_approval_to_memory(
    result: PreparationReviewResult, decision_log_path: Path
) -> DecisionEvent:
    if result.review_status != "approved":
        raise ValueError("Only an approved preparation review can enter memory")
    store = DecisionLogStore(decision_log_path)
    events = store.load()
    if not events:
        raise ValueError("Preparation review requires initialized project memory")
    summaries = [
        {
            "source_id": item.source_id,
            "predictor_id": item.predictor_id,
            "plan_version": result.plan_version,
            "native_frequency": item.native_frequency,
            "quarterly_aggregation_method": (
                item.quarterly_comparison.aggregation_method.value
                if item.quarterly_comparison else None
            ),
            "change_methods": [
                calculation.method.value for calculation in item.change_calculations
            ],
            "predictive_lag_periods": (
                item.predictive_alignment.lag_periods
                if item.predictive_alignment else None
            ),
            "rationale": item.rationale,
        }
        for item in result.approved_contracts
    ]
    digest_payload = {
        "contracts": summaries,
        "review_choice": result.review_choice,
        "custom_instructions": result.custom_instructions,
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:10]
    plan_slug = re.sub(r"[^a-z0-9_-]+", "_", result.plan_version.lower()).strip("_")
    event_id = f"preparation_approval_{plan_slug}_{digest}"
    if existing := next((item for item in events if item.event_id == event_id), None):
        return existing
    event = DecisionEvent(
        event_id=event_id,
        project_id=events[0].project_id,
        sequence=events[-1].sequence + 1,
        recorded_at=result.reviewed_at,
        actor="human",
        status="confirmed",
        decision_type="preparation_approval",
        payload={
            "contracts": summaries,
            "review_choice": result.review_choice,
            "custom_instructions": result.custom_instructions,
        },
        rationale="The human reviewer approved explicit deterministic preparation contracts.",
        evidence=[f"PreparationReview {result.plan_version}"],
    )
    store.append(event)
    return event


def preparation_review_node(state: PreparationReviewState) -> PreparationReviewState:
    proposal = DataPreparationProposal.model_validate(state["preparation_proposal"])
    validation = PreparationValidation.model_validate(state["preparation_validation"])
    submission = PreparationReviewSubmission.model_validate(
        state["preparation_review_submission"]
    )
    result = evaluate_preparation_review(
        proposal=proposal,
        validation=validation,
        approved_catalog_entries=state["approved_catalog_entries"],
        submission=submission,
    )
    if result.review_status == "approved" and state.get("memory_decision_log_path"):
        memory_events = DecisionLogStore(
            Path(state["memory_decision_log_path"])
        ).load()
        known_event_ids = {item.event_id for item in memory_events}
        basis_errors: list[str] = []
        for contract in result.approved_contracts:
            referenced = {
                item.removeprefix("memory_event:")
                for item in contract.decision_basis
                if item.startswith("memory_event:")
            }
            if unknown := referenced - known_event_ids:
                basis_errors.append(
                    f"{contract.source_id}: unknown memory events {sorted(unknown)}"
                )
        if basis_errors:
            result = result.model_copy(update={
                "review_status": "invalid",
                "approved_contracts": [],
                "errors": [*result.errors, *basis_errors],
            })
    memory_event = None
    if result.review_status == "approved" and state.get("memory_decision_log_path"):
        memory_event = append_preparation_approval_to_memory(
            result, Path(state["memory_decision_log_path"])
        )
    result_dict = result.model_dump(mode="json")
    contracts = [item.model_dump(mode="json") for item in result.approved_contracts]
    if state.get("preparation_review_artifact_dir"):
        directory = Path(state["preparation_review_artifact_dir"])
        _write_json(directory / "preparation_review_submission.json", submission.model_dump(mode="json"))
        _write_json(directory / "preparation_review_result.json", result_dict)
        if result.review_status == "approved":
            _write_json(directory / "approved_preparation_plan.json", {
                "plan_version": result.plan_version,
                "approved_by": result.reviewer,
                "approved_at": result_dict["reviewed_at"],
                "contracts": contracts,
            })
        if memory_event is not None:
            _write_json(directory / "preparation_memory_event.json", memory_event.model_dump(mode="json"))
    return {
        "preparation_review_result": result_dict,
        "approved_preparation_contracts": contracts,
        "preparation_memory_event": (
            memory_event.model_dump(mode="json") if memory_event else {}
        ),
    }
