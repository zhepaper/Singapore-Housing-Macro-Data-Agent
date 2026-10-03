from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from housing_agent.research.models import (
    AnalyticalRole,
    ApprovedResearchScope,
    MarketRole,
    StrictModel,
)


FORBIDDEN_MEMORY_KEY_PARTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "access_token",
    "refresh_token",
)


def _reject_secrets(value: object, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalised = str(key).lower().replace("-", "_")
            if any(part in normalised for part in FORBIDDEN_MEMORY_KEY_PARTS):
                raise ValueError(f"secret-like field is forbidden in memory: {path}.{key}")
            _reject_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secrets(child, f"{path}[{index}]")


class DecisionEvent(StrictModel):
    event_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    sequence: int = Field(ge=1)
    recorded_at: datetime
    actor: Literal["human", "system", "llm_proposal"]
    status: Literal["confirmed", "pending", "rejected"]
    decision_type: Literal[
        "scope",
        "research_preferences",
        "data_preferences",
        "analytical_preferences",
        "reporting_preferences",
        "predictor_approval",
        "preparation_approval",
        "pending_question",
    ]
    payload: dict[str, Any]
    rationale: str = Field(min_length=3)
    evidence: list[str]
    supersedes: str | None = None

    @field_validator("payload")
    @classmethod
    def payload_contains_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_secrets(value)
        return value


class ResearchPreferences(StrictModel):
    discovery_breadth: Literal["small_set", "retain_all_supported_candidates"]
    final_report_selection: Literal["pending", "small_set", "all_approved"]
    literature_required: bool
    singapore_specific_evidence_preferred: bool
    academic_citations_required: bool


class DataPreferences(StrictModel):
    preserve_native_frequency: bool
    allow_derived_alignment_views: bool
    preferred_comparison_frequency: str
    annual_interpolation_allowed: Literal[False] = False
    missing_values_as_zero: Literal[False] = False
    deterministic_calculation_required: bool


class AnalyticalPreferences(StrictModel):
    native_monitoring: bool
    contemporaneous_comparison: bool
    potential_predictive_alignment: bool
    causal_claims_allowed: Literal[False] = False
    forecast_model_required: bool


class ReportingPreferences(StrictModel):
    separate_sale_and_rent: bool
    distinguish_shared_predictors: bool
    include_limitations: bool
    include_source_links: bool
    include_data_frequency: bool
    concise_academic_style: bool


class ApprovedPredictorMemory(StrictModel):
    predictor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    selection_rationale: list[str] = Field(min_length=1)
    intended_market_role: MarketRole
    intended_analytical_role: AnalyticalRole
    review_version: int = Field(ge=1)


class PendingQuestion(StrictModel):
    question_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    topic: str = Field(min_length=3)
    question: str = Field(min_length=10)
    options: list[str] = Field(min_length=1)
    context: str = Field(min_length=10)


class ApprovedPreparationMemory(StrictModel):
    source_id: str
    predictor_id: str
    plan_version: str
    native_frequency: str
    quarterly_aggregation_method: str | None
    change_methods: list[str]
    predictive_lag_periods: int | None
    rationale: str


class MemorySnapshot(StrictModel):
    project_id: str
    memory_version: int = Field(ge=1)
    compiled_at: datetime
    approved_scope: ApprovedResearchScope
    research_preferences: ResearchPreferences
    data_preferences: DataPreferences
    analytical_preferences: AnalyticalPreferences
    reporting_preferences: ReportingPreferences
    approved_predictors: list[ApprovedPredictorMemory]
    approved_preparation_plans: list[ApprovedPreparationMemory] = Field(
        default_factory=list
    )
    pending_questions: list[PendingQuestion]
    source_event_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def approved_predictor_ids_are_unique(self) -> "MemorySnapshot":
        ids = [item.predictor_id for item in self.approved_predictors]
        if len(ids) != len(set(ids)):
            raise ValueError("approved predictor IDs must be unique in memory")
        return self


class MemoryManifest(StrictModel):
    project_id: str
    memory_version: int
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_path: str | None
    event_count: int = Field(ge=1)
    compiled_at: datetime
