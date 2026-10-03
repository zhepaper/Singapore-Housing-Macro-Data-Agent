from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from housing_agent.processing.models import MappingContract
from housing_agent.research.models import StrictModel


class FieldProfile(StrictModel):
    path: str
    observed_types: list[str]
    non_null_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    examples: list[str]


class TableProfile(StrictModel):
    location: str
    records_path: tuple[str | int, ...] = ()
    sheet_name: str | None = None
    header_row: int | None = None
    record_count: int = Field(ge=1)
    fields: list[FieldProfile] = Field(min_length=1)
    period_like_fields: list[str]
    likely_layout: Literal["long", "wide", "unknown"]
    sample_records: list[dict[str, Any]]


class RawSchemaProfile(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_id: str = Field(min_length=2)
    snapshot_path: str
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_format: Literal["json", "csv", "xlsx"]
    byte_count: int = Field(ge=1)
    tables: list[TableProfile] = Field(min_length=1)
    profiler_warnings: list[str]


class MappingProposal(StrictModel):
    proposal_version: Literal["1.0"] = "1.0"
    source_id: str
    series_id: str
    mapping_contract: MappingContract
    selected_table_location: str
    rationale: str = Field(min_length=30)
    confidence: Literal["high", "medium", "low"]
    assumptions: list[str]

    @model_validator(mode="after")
    def contract_identity_matches(self) -> "MappingProposal":
        if self.mapping_contract.source_id != self.source_id:
            raise ValueError("mapping contract source_id differs from proposal")
        if self.mapping_contract.series_id != self.series_id:
            raise ValueError("mapping contract series_id differs from proposal")
        return self


class MappedValue(StrictModel):
    period: str | None
    value: str | None
    raw_period: str
    raw_value: str | None
    raw_record_reference: str


class MappingExecutionReport(StrictModel):
    source_id: str
    series_id: str
    status: Literal["pass", "fail"]
    selected_record_count: int = Field(ge=0)
    extracted_observation_count: int = Field(ge=0)
    parsed_observation_count: int = Field(ge=0)
    non_null_observation_count: int = Field(ge=0)
    missing_observation_count: int = Field(ge=0)
    duplicate_periods: list[str]
    observed_period_start: str | None
    observed_period_end: str | None
    observations: list[MappedValue]
    errors: list[str]
    warnings: list[str]


class MappingAttempt(StrictModel):
    attempt: int = Field(ge=1, le=3)
    proposal: MappingProposal | None
    execution: MappingExecutionReport | None
    provider_metadata: dict[str, Any]
    error_feedback: list[str]


class AdaptiveMappingResult(StrictModel):
    status: Literal["ready_for_human_review", "mapping_recovery_exhausted", "failed"]
    source_id: str
    series_id: str
    schema_profile: RawSchemaProfile
    accepted_proposal: MappingProposal | None
    accepted_execution: MappingExecutionReport | None
    attempts: list[MappingAttempt] = Field(min_length=1, max_length=3)
    errors: list[str]


class SeriesRoleAssignment(StrictModel):
    source_id: str
    series_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    series_label: str = Field(min_length=2)
    portfolio_role: Literal["outcome", "predictor", "structural_context"]
    market_role: Literal["sale", "rent", "shared"]
    release_lag_days: int = Field(default=0, ge=0)
    minimum_observations: int = Field(default=2, ge=1)
    max_staleness_periods: int = Field(default=4, ge=0)
    duplicate_policy: Literal["error", "latest_release"] = "error"


class UnifiedSourceDecision(StrictModel):
    source_id: str
    decision: Literal["approve", "request_mapping_revision", "replace_source", "reject"]
    role_assignment: SeriesRoleAssignment | None
    review_notes: list[str]

    @model_validator(mode="after")
    def approval_has_role(self) -> "UnifiedSourceDecision":
        if self.decision == "approve" and self.role_assignment is None:
            raise ValueError("source approval requires a role_assignment")
        if self.decision != "approve" and not any(item.strip() for item in self.review_notes):
            raise ValueError("non-approval decisions require review notes")
        return self


class UnifiedDataPlanReviewSubmission(StrictModel):
    plan_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    plan_version: int = Field(ge=1)
    reviewer: str = Field(min_length=2)
    confirmation_status: Literal["draft", "confirmed"]
    reporting_as_of_date: date
    historical_start_date: date
    historical_end_date: date
    minimum_quarterly_observations: int = Field(default=8, ge=1)
    feature_redundancy_threshold: str = "0.95"
    source_decisions: list[UnifiedSourceDecision] = Field(min_length=1)
    overall_notes: list[str]

    @model_validator(mode="after")
    def unique_sources_and_valid_window(self) -> "UnifiedDataPlanReviewSubmission":
        ids = [item.source_id for item in self.source_decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("source decisions must have unique source IDs")
        if self.historical_start_date > self.historical_end_date:
            raise ValueError("historical start must not follow historical end")
        if self.historical_end_date > self.reporting_as_of_date:
            raise ValueError("historical end must not follow reporting as-of date")
        return self


class UnifiedDataPlanReviewResult(StrictModel):
    status: Literal["approved", "needs_mapping_revision", "replace_source", "rejected", "invalid"]
    reviewer: str
    reviewed_at: datetime
    approved_source_ids: list[str]
    revision_source_ids: list[str]
    replacement_source_ids: list[str]
    rejected_source_ids: list[str]
    frozen_plan_path: str | None
    errors: list[str]
    warnings: list[str]
