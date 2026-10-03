from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from housing_agent.research.models import PredictorCandidate, StrictModel
from housing_agent.onboarding.discovery_models import DraftCatalogEntry
from housing_agent.onboarding.discovery_models import migrate_legacy_draft_catalog_entry


class CandidateReviewSubmission(StrictModel):
    predictor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    decision: Literal["approve", "reject", "request_revision"]
    review_notes: list[str]
    selection_rationale: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_approval_rationale(cls, value):
        if isinstance(value, dict) and value.get("decision") == "approve":
            if not value.get("selection_rationale") and value.get("review_notes"):
                value = dict(value)
                value["selection_rationale"] = list(value["review_notes"])
        return value

    @model_validator(mode="after")
    def explanation_required_for_non_approval(self) -> "CandidateReviewSubmission":
        if self.decision == "approve" and not any(
            note.strip() for note in self.selection_rationale
        ):
            raise ValueError("approve decisions require a selection rationale")
        if self.decision != "approve" and not any(
            note.strip() for note in self.review_notes
        ):
            raise ValueError("reject and request_revision decisions require a review note")
        return self


class PredictorReviewSubmission(StrictModel):
    review_version: int = Field(ge=1)
    reviewer: str = Field(min_length=2)
    candidate_reviews: list[CandidateReviewSubmission] = Field(min_length=1)
    overall_notes: list[str]

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> "PredictorReviewSubmission":
        ids = [item.predictor_id for item in self.candidate_reviews]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_reviews must contain each predictor at most once")
        return self


class PredictorReviewResult(StrictModel):
    review_status: Literal["approved", "needs_revision", "rejected", "invalid"]
    review_version: int
    reviewer: str
    reviewed_at: datetime
    approved_predictor_ids: list[str]
    rejected_predictor_ids: list[str]
    revision_requested_ids: list[str]
    covered_scope_pairs: list[str]
    approved_predictors: list[PredictorCandidate]
    selection_rationales: dict[str, list[str]]
    errors: list[str]
    warnings: list[str]


class CatalogCandidateReview(StrictModel):
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    decision: Literal["approve", "reject", "request_revision"]
    review_notes: list[str]

    @model_validator(mode="after")
    def notes_required_for_non_approval(self) -> "CatalogCandidateReview":
        if self.decision != "approve" and not any(
            note.strip() for note in self.review_notes
        ):
            raise ValueError("reject and request_revision decisions require a review note")
        return self


class CatalogReviewSubmission(StrictModel):
    catalog_version: str = Field(min_length=1)
    reviewer: str = Field(min_length=2)
    candidate_reviews: list[CatalogCandidateReview] = Field(min_length=1)
    overall_notes: list[str]

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> "CatalogReviewSubmission":
        ids = [item.candidate_id for item in self.candidate_reviews]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_reviews must contain each candidate at most once")
        return self


class ApprovedCatalogEntry(StrictModel):
    catalog_version: str
    approved_by: str
    approved_at: datetime
    entry: DraftCatalogEntry


def load_approved_catalog_entry(value: dict) -> ApprovedCatalogEntry:
    migrated = dict(value)
    migrated["entry"] = migrate_legacy_draft_catalog_entry(value["entry"])
    return ApprovedCatalogEntry.model_validate(migrated)


class CatalogReviewResult(StrictModel):
    review_status: Literal["approved", "needs_revision", "rejected", "invalid"]
    catalog_version: str
    reviewer: str
    reviewed_at: datetime
    approved_candidate_ids: list[str]
    rejected_candidate_ids: list[str]
    revision_requested_ids: list[str]
    approved_entries: list[ApprovedCatalogEntry]
    errors: list[str]
    warnings: list[str]
