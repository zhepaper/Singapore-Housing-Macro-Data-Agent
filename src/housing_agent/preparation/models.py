from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from housing_agent.onboarding.discovery_models import AggregationMethod, ChangeMethod
from housing_agent.research.models import StrictModel


class ChangeCalculation(StrictModel):
    input_view: Literal["native", "quarterly_comparison"]
    horizon: Literal["mom", "qoq", "yoy", "period_change"]
    method: ChangeMethod
    lag_periods: int = Field(ge=1, le=24)
    rationale: str = Field(min_length=20)


class QuarterlyComparisonView(StrictModel):
    target_frequency: Literal["quarterly"] = "quarterly"
    aggregation_method: AggregationMethod
    incomplete_period_policy: Literal["reject", "mark_partial"]
    rationale: str = Field(min_length=20)


class PredictiveAlignment(StrictModel):
    target_outcome_frequency: Literal["quarterly"] = "quarterly"
    lag_periods: int = Field(ge=1, le=4)
    interpretation: Literal["exploratory_predictive_alignment"] = (
        "exploratory_predictive_alignment"
    )
    rationale: str = Field(min_length=20)


class PreparationContract(StrictModel):
    source_id: str = Field(min_length=2)
    predictor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    native_frequency: Literal["monthly", "quarterly", "annual"]
    preserve_native_view: Literal[True] = True
    quarterly_comparison: QuarterlyComparisonView | None
    change_calculations: list[ChangeCalculation] = Field(default_factory=list)
    predictive_alignment: PredictiveAlignment | None
    missing_value_policy: Literal["preserve_null"] = "preserve_null"
    interpolation_allowed: Literal[False] = False
    rationale: str = Field(min_length=30)
    decision_basis: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def view_references_exist(self) -> "PreparationContract":
        if self.quarterly_comparison is None and any(
            item.input_view == "quarterly_comparison"
            for item in self.change_calculations
        ):
            raise ValueError(
                "quarterly_comparison calculations require a comparison view"
            )
        return self


class PreparationRecommendation(StrictModel):
    source_profile_summary: str = Field(min_length=30)
    market_use_summary: str = Field(min_length=30, max_length=180)
    contract: PreparationContract
    alternatives_considered: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


class DataPreparationProposal(StrictModel):
    project_id: str
    memory_version: int = Field(ge=1)
    memory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    structured_data_overview: str = Field(min_length=80)
    concise_recommendation: str = Field(min_length=40, max_length=1200)
    recommendations: list[PreparationRecommendation] = Field(min_length=1)
    unresolved_questions: list[str]
    proposal_limitations: list[str] = Field(min_length=1)


class RawSnapshotEvidence(StrictModel):
    source_id: str = Field(min_length=2)
    status: Literal["pass", "fail"]
    retrieval_url: str
    retrieved_at: datetime
    http_status: int | None
    content_type: str | None
    byte_count: int
    sha256: str | None
    snapshot_path: str | None
    preview_records: list[dict[str, Any]]
    observed_period_start: str | None = None
    observed_period_end: str | None = None
    non_null_observation_count: int | None = None
    errors: list[str]


class SeriesInventoryRow(StrictModel):
    source_id: str
    predictor_id: str
    series: str
    market_use: str
    public_source: str
    source_url: str
    raw_snapshot: Literal["saved", "failed"]
    raw_snapshot_path: str | None
    definition: str
    unit: str
    observation_frequency: str
    update_frequency: str
    raw_coverage: str
    validation: Literal["pass", "fail"]
    recommended_transformation: str


class PreparationReviewView(StrictModel):
    title: str = "Data Inventory and Preparation Review"
    inventory: list[SeriesInventoryRow] = Field(min_length=1)
    concise_recommendation: str
    requirements_checklist: list[str] = Field(min_length=5)
    review_options: list[str] = Field(min_length=5)
    custom_instruction_prompt: str
    important_note: str
    markdown: str


class ContractValidation(StrictModel):
    source_id: str
    status: Literal["pass", "fail"]
    errors: list[str]
    warnings: list[str]


class PreparationValidation(StrictModel):
    automated_validation_status: Literal["pass", "fail"]
    human_review_status: Literal["pending", "not_ready"]
    contract_validations: list[ContractValidation]
    errors: list[str]
    warnings: list[str]


class PreparationReviewItem(StrictModel):
    source_id: str = Field(min_length=2)
    decision: Literal["approve", "reject", "request_revision"]
    approved_contract: PreparationContract | None
    review_notes: list[str]

    @model_validator(mode="after")
    def decision_has_required_content(self) -> "PreparationReviewItem":
        if self.decision == "approve" and self.approved_contract is None:
            raise ValueError("approve requires an explicit approved_contract")
        if self.decision != "approve" and self.approved_contract is not None:
            raise ValueError("only approve may contain approved_contract")
        if self.decision != "approve" and not any(
            item.strip() for item in self.review_notes
        ):
            raise ValueError("reject and request_revision require review notes")
        return self


class PreparationReviewSubmission(StrictModel):
    plan_version: str = Field(min_length=1)
    reviewer: str = Field(min_length=2)
    review_choice: Literal[
        "approve_all",
        "modify_transformations",
        "replace_sources",
        "custom_instructions",
        "reject_proposal",
    ]
    custom_instructions: str | None = None
    confirmation_status: Literal["draft", "confirmed"] = "draft"
    source_reviews: list[PreparationReviewItem] = Field(min_length=1)
    overall_notes: list[str]

    @model_validator(mode="after")
    def source_ids_are_unique(self) -> "PreparationReviewSubmission":
        ids = [item.source_id for item in self.source_reviews]
        if len(ids) != len(set(ids)):
            raise ValueError("source_reviews must contain unique source IDs")
        if self.review_choice == "custom_instructions" and not (
            self.custom_instructions and self.custom_instructions.strip()
        ):
            raise ValueError("custom_instructions choice requires written instructions")
        return self


class PreparationReviewResult(StrictModel):
    review_status: Literal["approved", "needs_revision", "rejected", "invalid"]
    plan_version: str
    reviewer: str
    reviewed_at: datetime
    review_choice: Literal[
        "approve_all",
        "modify_transformations",
        "replace_sources",
        "custom_instructions",
        "reject_proposal",
    ]
    custom_instructions: str | None
    approved_contracts: list[PreparationContract]
    rejected_source_ids: list[str]
    revision_requested_source_ids: list[str]
    errors: list[str]
    warnings: list[str]


class ExecutionTrace(StrictModel):
    source_id: str
    input_observations: int
    native_observations: int
    comparison_observations: int
    change_observations: int
    output_observations: int
    operations: list[str]
