from __future__ import annotations

from enum import Enum
from typing import Any, Literal
import copy

from pydantic import Field, field_validator, model_validator

from housing_agent.research.models import StrictModel, _require_http_url


class DiscoverySourceType(str, Enum):
    DATAGOV_JSON = "datagov_json"
    GENERIC_JSON = "generic_json"
    CSV = "csv"
    HTML_REPORT = "html_report"
    XLSX = "xlsx"


class SeriesType(str, Enum):
    STOCK = "stock"
    FLOW = "flow"
    RATE = "rate"
    INDEX = "index"


class AggregationMethod(str, Enum):
    PRESERVE = "preserve"
    LAST = "last"
    MEAN = "mean"
    SUM = "sum"
    NOT_APPLICABLE = "not_applicable"


class ChangeMethod(str, Enum):
    ABSOLUTE = "absolute_change"
    PERCENT = "percentage_change"
    PERCENTAGE_POINT = "percentage_point_change"
    BASIS_POINT = "basis_point_change"
    PUBLISHED_CHANGE = "preserve_published_change"


class DiscoveryQuery(StrictModel):
    query: str = Field(min_length=8)
    purpose: str = Field(min_length=8)


class ProposedTransformation(StrictModel):
    series_type: SeriesType
    target_frequency: str = Field(min_length=2)
    aggregation_method: AggregationMethod
    change_methods: list[ChangeMethod] = Field(min_length=1)
    incomplete_period_policy: Literal["reject", "mark_partial", "not_applicable"]
    interpolation_allowed: Literal[False] = False
    rationale: str = Field(min_length=20)


class DataSourceCandidate(StrictModel):
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    predictor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    official_agency: str = Field(min_length=3)
    dataset_title: str = Field(min_length=5)
    source_type: DiscoverySourceType
    source_page_url: str
    retrieval_url: str
    definition_url: str | None
    dataset_id: str | None
    table_id: str | None
    definition: str = Field(min_length=20)
    unit: str = Field(min_length=1)
    native_frequency: str = Field(min_length=2)
    update_frequency: str = Field(min_length=2)
    series_identifier: str = Field(min_length=5)
    schema_orientation: Literal["long_records", "wide_period_columns"]
    date_field_candidates: list[str] = Field(min_length=1)
    value_field_candidates: list[str] = Field(min_length=1)
    series_field: str | None
    wide_period_format: Literal["singstat_month", "singstat_quarter"] | None
    exact_series_label: str | None
    series_type: SeriesType
    point_in_time_notes: str = Field(min_length=20)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def orientation_fields_are_consistent(self) -> "DataSourceCandidate":
        if self.schema_orientation == "wide_period_columns":
            if not self.series_field or not self.wide_period_format:
                raise ValueError(
                    "wide_period_columns requires series_field and wide_period_format"
                )
        elif self.wide_period_format is not None:
            raise ValueError("long_records must not set wide_period_format")
        return self

    @field_validator("source_page_url", "retrieval_url")
    @classmethod
    def valid_required_urls(cls, value: str) -> str:
        return _require_http_url(value)

    @field_validator("definition_url")
    @classmethod
    def valid_optional_url(cls, value: str | None) -> str | None:
        return _require_http_url(value) if value else value


class DataDiscoveryProposal(StrictModel):
    predictor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    scope_summary: str = Field(min_length=20)
    search_queries: list[DiscoveryQuery] = Field(min_length=1)
    candidates: list[DataSourceCandidate] = Field(min_length=1, max_length=2)
    rejected_sources: list[str]
    unresolved_questions: list[str]

    @model_validator(mode="after")
    def candidate_predictors_match(self) -> "DataDiscoveryProposal":
        mismatched = [
            item.candidate_id
            for item in self.candidates
            if item.predictor_id != self.predictor_id
        ]
        if mismatched:
            raise ValueError(
                f"candidate predictor IDs do not match proposal: {mismatched}"
            )
        return self


class SourceProbeResult(StrictModel):
    candidate_id: str
    status: Literal["pass", "fail"]
    requested_url: str
    final_url: str | None
    http_status: int | None
    content_type: str | None
    bytes_sampled: int
    detected_format: str | None
    fields: list[str]
    sample_record_count: int
    total_record_count: int | None
    date_field_matches: list[str]
    value_field_matches: list[str]
    series_field_match: str | None
    field_adjustments: list[str]
    observed_period_start: str | None = None
    observed_period_end: str | None = None
    non_null_observation_count: int | None = None
    missing_observation_count: int | None = None
    coverage_profile_scope: Literal[
        "full_response_series", "sample_records", "unavailable"
    ] = "unavailable"
    errors: list[str]
    warnings: list[str]


class DiscoveryCandidateScore(StrictModel):
    candidate_id: str
    total_score: int = Field(ge=0, le=100)
    score_breakdown: dict[str, int]
    hard_gate_status: Literal["pass", "fail"]
    hard_gate_failures: list[str]


class DataDiscoveryValidation(StrictModel):
    automated_validation_status: Literal["pass", "fail"]
    human_review_status: Literal["pending", "not_ready"]
    errors: list[str]
    warnings: list[str]
    candidate_scores: list[DiscoveryCandidateScore]


class DraftCatalogEntry(StrictModel):
    draft_status: Literal["unapproved"] = "unapproved"
    predictor_id: str
    candidate_id: str
    source_id: str
    official_agency: str
    dataset_title: str
    source_type: DiscoverySourceType
    source_page_url: str
    retrieval_url: str
    definition_url: str | None
    dataset_id: str | None
    table_id: str | None
    definition: str
    unit: str
    native_frequency: str
    update_frequency: str
    series_identifier: str
    schema_orientation: Literal["long_records", "wide_period_columns"]
    series_field: str | None
    wide_period_format: Literal["singstat_month", "singstat_quarter"] | None
    proposed_date_field: str
    proposed_value_field: str
    exact_series_label: str | None
    series_type: SeriesType
    point_in_time_notes: str
    limitations: list[str]
    probe: SourceProbeResult


def migrate_legacy_data_source_candidate(value: dict[str, Any]) -> dict[str, Any]:
    """Remove v1 operation advice while retaining its structural series classification."""
    migrated = copy.deepcopy(value)
    legacy = migrated.pop("proposed_transformation", None)
    if "series_type" not in migrated and isinstance(legacy, dict):
        migrated["series_type"] = legacy.get("series_type")
    return migrated


def load_data_source_candidate(value: dict[str, Any]) -> DataSourceCandidate:
    return DataSourceCandidate.model_validate(migrate_legacy_data_source_candidate(value))


def migrate_legacy_discovery_proposal(value: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(value)
    migrated["candidates"] = [
        migrate_legacy_data_source_candidate(item)
        for item in migrated.get("candidates", [])
    ]
    return migrated


def load_discovery_proposal(value: dict[str, Any]) -> DataDiscoveryProposal:
    return DataDiscoveryProposal.model_validate(migrate_legacy_discovery_proposal(value))


def migrate_legacy_draft_catalog_entry(value: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(value)
    legacy = migrated.pop("transformation_contract", None)
    if "series_type" not in migrated and isinstance(legacy, dict):
        migrated["series_type"] = legacy.get("series_type")
    return migrated


def load_draft_catalog_entry(value: dict[str, Any]) -> DraftCatalogEntry:
    return DraftCatalogEntry.model_validate(migrate_legacy_draft_catalog_entry(value))
