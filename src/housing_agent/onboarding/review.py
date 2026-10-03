from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from housing_agent.onboarding.models import (
    PredictorReviewResult,
    PredictorReviewSubmission,
)
from housing_agent.memory.models import DecisionEvent
from housing_agent.memory.store import DecisionLogStore
from housing_agent.research.models import (
    ApprovedResearchScope,
    ResearchProposal,
    ResearchValidationResult,
    load_research_proposal,
)


class PredictorReviewState(TypedDict, total=False):
    approved_scope: dict[str, Any]
    research_proposal: dict[str, Any]
    research_validation: dict[str, Any]
    predictor_review_submission: dict[str, Any]
    predictor_review_artifact_dir: str
    predictor_review_result: dict[str, Any]
    approved_predictors: list[dict[str, Any]]
    memory_decision_log_path: str
    predictor_approval_memory_event: dict[str, Any]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate_predictor_review(
    *,
    scope: ApprovedResearchScope,
    proposal: ResearchProposal,
    validation: ResearchValidationResult,
    submission: PredictorReviewSubmission,
) -> PredictorReviewResult:
    errors: list[str] = []
    warnings: list[str] = []
    candidate_by_id = {item.predictor_id: item for item in proposal.candidates}
    expected_ids = set(candidate_by_id)
    submitted_ids = {item.predictor_id for item in submission.candidate_reviews}

    if validation.automated_validation_status != "pass":
        errors.append("Predictors cannot be approved until automated research validation passes.")
    missing = expected_ids - submitted_ids
    unknown = submitted_ids - expected_ids
    if missing:
        errors.append(f"Review decisions are missing for predictors: {sorted(missing)}")
    if unknown:
        errors.append(f"Review contains unknown predictor IDs: {sorted(unknown)}")

    score_by_id = {item.predictor_id: item for item in validation.candidate_scores}
    approved_ids: list[str] = []
    rejected_ids: list[str] = []
    revision_ids: list[str] = []
    for review in submission.candidate_reviews:
        if review.predictor_id not in candidate_by_id:
            continue
        if review.decision == "approve":
            score = score_by_id.get(review.predictor_id)
            if score is None or score.hard_gate_status != "pass":
                errors.append(
                    f"{review.predictor_id} cannot be approved because its research hard gate did not pass."
                )
            else:
                approved_ids.append(review.predictor_id)
        elif review.decision == "reject":
            rejected_ids.append(review.predictor_id)
        else:
            revision_ids.append(review.predictor_id)

    approved = [candidate_by_id[item] for item in approved_ids]
    rationale_by_id = {
        item.predictor_id: item.selection_rationale
        for item in submission.candidate_reviews
        if item.predictor_id in approved_ids
    }
    covered_pairs = sorted({
        f"{mechanism.housing_segment.value}/{mechanism.market.value}"
        for candidate in approved
        for mechanism in candidate.mechanisms
        if mechanism.relevance.value == "primary"
    })
    required_pairs = {
        f"{segment.value}/{market.value}"
        for segment in scope.housing_segments
        for market in scope.markets
    }
    missing_pairs = required_pairs - set(covered_pairs)
    if approved and missing_pairs:
        errors.append(
            "Approved predictors do not retain primary mechanism coverage for: "
            f"{sorted(missing_pairs)}"
        )

    if errors:
        status = "invalid"
    elif revision_ids:
        status = "needs_revision"
    elif approved_ids:
        status = "approved"
    else:
        status = "rejected"
        warnings.append("All proposed predictors were rejected; discovery cannot start.")

    return PredictorReviewResult(
        review_status=status,
        review_version=submission.review_version,
        reviewer=submission.reviewer,
        reviewed_at=datetime.now(timezone.utc),
        approved_predictor_ids=approved_ids,
        rejected_predictor_ids=rejected_ids,
        revision_requested_ids=revision_ids,
        covered_scope_pairs=covered_pairs,
        approved_predictors=approved,
        selection_rationales=rationale_by_id,
        errors=errors,
        warnings=warnings,
    )


def append_predictor_approval_to_memory(
    *,
    result: PredictorReviewResult,
    decision_log_path: Path,
) -> DecisionEvent:
    """Append an idempotent, human-approved predictor decision to project memory."""
    if result.review_status != "approved":
        raise ValueError("only an approved predictor review can be written to memory")
    store = DecisionLogStore(decision_log_path)
    events = store.load()
    if not events:
        raise ValueError("predictor review requires an initialized project decision log")
    digest_input = json.dumps(
        {
            "review_version": result.review_version,
            "predictor_ids": result.approved_predictor_ids,
            "selection_rationales": result.selection_rationales,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    event_id = (
        f"predictor_approval_review_{result.review_version}_"
        f"{hashlib.sha256(digest_input).hexdigest()[:10]}"
    )
    existing = next((item for item in events if item.event_id == event_id), None)
    if existing is not None:
        return existing
    previous = next(
        (
            item for item in reversed(events)
            if item.decision_type == "predictor_approval"
            and item.status == "confirmed"
        ),
        None,
    )
    event = DecisionEvent(
        event_id=event_id,
        project_id=events[0].project_id,
        sequence=events[-1].sequence + 1,
        recorded_at=result.reviewed_at,
        actor="human",
        status="confirmed",
        decision_type="predictor_approval",
        payload={
            "predictors": [
                {
                    "predictor_id": item.predictor_id,
                    "selection_rationale": result.selection_rationales[item.predictor_id],
                    "intended_market_role": item.market_role.value,
                    "intended_analytical_role": item.analytical_role.value,
                    "review_version": result.review_version,
                }
                for item in result.approved_predictors
            ]
        },
        rationale=(
            "The human reviewer approved these literature-supported predictor "
            "concepts and recorded a selection rationale for each one."
        ),
        evidence=[f"PredictorReview version {result.review_version}"],
        supersedes=previous.event_id if previous is not None else None,
    )
    store.append(event)
    return event


def review_predictors_node(state: PredictorReviewState) -> PredictorReviewState:
    scope = ApprovedResearchScope.model_validate(state["approved_scope"])
    proposal = load_research_proposal(state["research_proposal"])
    validation = ResearchValidationResult.model_validate(state["research_validation"])
    submission = PredictorReviewSubmission.model_validate(
        state["predictor_review_submission"]
    )
    result = evaluate_predictor_review(
        scope=scope,
        proposal=proposal,
        validation=validation,
        submission=submission,
    )
    result_dict = result.model_dump(mode="json")
    memory_event: DecisionEvent | None = None
    if result.review_status == "approved" and state.get("memory_decision_log_path"):
        memory_event = append_predictor_approval_to_memory(
            result=result,
            decision_log_path=Path(state["memory_decision_log_path"]),
        )
    artifact_dir = state.get("predictor_review_artifact_dir")
    if artifact_dir:
        directory = Path(artifact_dir)
        _write_json(directory / "predictor_review_submission.json", submission.model_dump(mode="json"))
        _write_json(directory / "predictor_review_result.json", result_dict)
        if result.review_status == "approved":
            _write_json(directory / "approved_predictors.json", {
                "review_version": result.review_version,
                "reviewed_at": result_dict["reviewed_at"],
                "selection_rationales": result.selection_rationales,
                "predictors": [item.model_dump(mode="json") for item in result.approved_predictors],
            })
        if memory_event is not None:
            _write_json(
                directory / "predictor_approval_memory_event.json",
                memory_event.model_dump(mode="json"),
            )
    return {
        "predictor_review_result": result_dict,
        "approved_predictors": [
            item.model_dump(mode="json") for item in result.approved_predictors
        ],
        "predictor_approval_memory_event": (
            memory_event.model_dump(mode="json") if memory_event is not None else {}
        ),
    }
