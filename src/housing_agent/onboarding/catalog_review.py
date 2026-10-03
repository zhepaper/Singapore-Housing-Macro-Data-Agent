from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from housing_agent.onboarding.discovery_models import (
    DraftCatalogEntry,
    load_draft_catalog_entry,
)
from housing_agent.onboarding.models import (
    ApprovedCatalogEntry,
    CatalogReviewResult,
    CatalogReviewSubmission,
)


class CatalogReviewState(TypedDict, total=False):
    draft_catalog_entries: list[dict[str, Any]]
    catalog_review_submission: dict[str, Any]
    catalog_review_artifact_dir: str
    catalog_review_result: dict[str, Any]
    approved_catalog_entries: list[dict[str, Any]]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _semantic_contract_errors(entry: DraftCatalogEntry) -> list[str]:
    errors: list[str] = []
    if entry.schema_orientation == "wide_period_columns":
        if entry.proposed_date_field != "__period_column__" or entry.proposed_value_field != "__period_value__":
            errors.append(f"{entry.candidate_id}: invalid wide-schema placeholders")
        if not entry.series_field or not entry.exact_series_label:
            errors.append(
                f"{entry.candidate_id}: a wide multi-series source requires an exact series selector"
            )
    if entry.probe.status != "pass":
        errors.append(f"{entry.candidate_id}: source probe did not pass")
    return errors


def evaluate_catalog_review(
    entries: list[DraftCatalogEntry], submission: CatalogReviewSubmission
) -> CatalogReviewResult:
    errors: list[str] = []
    warnings: list[str] = []
    entry_by_id = {entry.candidate_id: entry for entry in entries}
    expected = set(entry_by_id)
    submitted = {item.candidate_id for item in submission.candidate_reviews}
    missing = expected - submitted
    unknown = submitted - expected
    if missing:
        errors.append(f"Catalog review decisions are missing for: {sorted(missing)}")
    if unknown:
        errors.append(f"Catalog review contains unknown candidates: {sorted(unknown)}")

    approved_ids: list[str] = []
    rejected_ids: list[str] = []
    revision_ids: list[str] = []
    for review in submission.candidate_reviews:
        entry = entry_by_id.get(review.candidate_id)
        if entry is None:
            continue
        if review.decision == "approve":
            semantic_errors = _semantic_contract_errors(entry)
            if semantic_errors:
                errors.extend(semantic_errors)
            else:
                approved_ids.append(review.candidate_id)
        elif review.decision == "reject":
            rejected_ids.append(review.candidate_id)
        else:
            revision_ids.append(review.candidate_id)

    approved_by_predictor: dict[str, list[str]] = {}
    for candidate_id in approved_ids:
        entry = entry_by_id[candidate_id]
        approved_by_predictor.setdefault(entry.predictor_id, []).append(candidate_id)
    for predictor_id, candidate_ids in approved_by_predictor.items():
        if len(candidate_ids) > 1:
            errors.append(
                f"DataDiscovery v1 allows one approved primary source per predictor; {predictor_id} has {candidate_ids}"
            )

    reviewed_at = datetime.now(timezone.utc)
    approved_entries = [
        ApprovedCatalogEntry(
            catalog_version=submission.catalog_version,
            approved_by=submission.reviewer,
            approved_at=reviewed_at,
            entry=entry_by_id[candidate_id],
        )
        for candidate_id in approved_ids
    ]
    if errors:
        status = "invalid"
        approved_entries = []
    elif revision_ids:
        status = "needs_revision"
        approved_entries = []
    elif approved_ids:
        status = "approved"
    else:
        status = "rejected"
        warnings.append("No discovery candidate was approved for catalog onboarding.")
    return CatalogReviewResult(
        review_status=status,
        catalog_version=submission.catalog_version,
        reviewer=submission.reviewer,
        reviewed_at=reviewed_at,
        approved_candidate_ids=approved_ids,
        rejected_candidate_ids=rejected_ids,
        revision_requested_ids=revision_ids,
        approved_entries=approved_entries,
        errors=errors,
        warnings=warnings,
    )


def catalog_review_node(state: CatalogReviewState) -> CatalogReviewState:
    entries = [load_draft_catalog_entry(item) for item in state["draft_catalog_entries"]]
    submission = CatalogReviewSubmission.model_validate(state["catalog_review_submission"])
    result = evaluate_catalog_review(entries, submission)
    result_dict = result.model_dump(mode="json")
    approved = [item.model_dump(mode="json") for item in result.approved_entries]
    artifact_dir = state.get("catalog_review_artifact_dir")
    if artifact_dir:
        directory = Path(artifact_dir)
        _write_json(directory / "catalog_review_submission.json", submission.model_dump(mode="json"))
        _write_json(directory / "catalog_review_result.json", result_dict)
        if result.review_status == "approved":
            _write_json(directory / "approved_catalog_fragment.json", {
                "catalog_version": result.catalog_version,
                "catalog_status": "human_approved_fragment",
                "approved_entries": approved,
            })
    return {
        "catalog_review_result": result_dict,
        "approved_catalog_entries": approved,
    }
