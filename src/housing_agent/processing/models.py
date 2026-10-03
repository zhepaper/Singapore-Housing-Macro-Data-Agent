from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from housing_agent.onboarding.discovery_models import SeriesType
from housing_agent.preparation.models import PreparationContract
from housing_agent.research.models import StrictModel


class FrozenStrictModel(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RecoveryRoute(str, Enum):
    MAPPING_RECOVERY = "mapping_recovery"
    DATA_DISCOVERY = "data_discovery"
    HUMAN_REVIEW = "human_review"
    HARD_STOP = "hard_stop"


class MappingContract(FrozenStrictModel):
    contract_version: str = Field(min_length=1)
    source_id: str = Field(min_length=2)
    series_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    source_format: Literal["json", "csv", "xlsx"]
    layout: Literal["long", "wide"]
    records_path: tuple[str | int, ...] = ()
    sheet_name: str | None = None
    header_row: int = Field(default=1, ge=1)
    series_filter_field: str | None = None
    series_filter_value: str | None = None
    date_field: str | None = None
    value_field: str | None = None
    release_date_field: str | None = None
    revision_field: str | None = None
    wide_period_pattern: str | None = None
    period_format: Literal[
        "auto", "year", "quarter", "month", "singstat_quarter", "singstat_month"
    ] = "auto"
    missing_markers: tuple[str, ...] = ("", "-", "..", "na", "n.a.", "null")
    unit_scale: Decimal = Decimal("1")

    @model_validator(mode="after")
    def fields_match_layout(self) -> "MappingContract":
        if self.layout == "long" and (not self.date_field or not self.value_field):
            raise ValueError("long layout requires date_field and value_field")
        if self.layout == "wide" and not self.wide_period_pattern:
            raise ValueError("wide layout requires wide_period_pattern")
        if (self.series_filter_field is None) != (self.series_filter_value is None):
            raise ValueError("series filter field and value must be supplied together")
        if self.source_format != "xlsx" and self.sheet_name is not None:
            raise ValueError("sheet_name is only valid for xlsx sources")
        return self


class FrozenSeriesPlan(FrozenStrictModel):
    source_id: str = Field(min_length=2)
    series_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    series_label: str = Field(min_length=2)
    snapshot_path: str = Field(min_length=1)
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_contract: MappingContract
    preparation_contract: PreparationContract
    definition: str = Field(min_length=10)
    unit: str = Field(min_length=1)
    observation_frequency: Literal["monthly", "quarterly", "annual"]
    update_frequency: str = Field(min_length=2)
    series_type: SeriesType
    portfolio_role: Literal["outcome", "predictor", "structural_context"]
    market_role: Literal["sale", "rent", "shared"]
    release_lag_days: int = Field(default=0, ge=0)
    minimum_observations: int = Field(default=2, ge=1)
    max_staleness_periods: int = Field(default=4, ge=0)
    duplicate_policy: Literal["error", "latest_release"] = "error"

    @model_validator(mode="after")
    def contracts_match_series(self) -> "FrozenSeriesPlan":
        if self.mapping_contract.source_id != self.source_id:
            raise ValueError("mapping contract source_id does not match series plan")
        if self.mapping_contract.series_id != self.series_id:
            raise ValueError("mapping contract series_id does not match series plan")
        if self.preparation_contract.source_id != self.source_id:
            raise ValueError("preparation contract source_id does not match series plan")
        if self.preparation_contract.native_frequency != self.observation_frequency:
            raise ValueError("preparation contract frequency does not match series plan")
        return self


class FrozenDataPlan(FrozenStrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    plan_version: int = Field(ge=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_status: Literal["approved"]
    approved_by: str = Field(min_length=2)
    approved_at: datetime
    reporting_as_of_date: date
    historical_start_date: date
    historical_end_date: date
    minimum_quarterly_observations: int = Field(default=8, ge=1)
    feature_redundancy_threshold: Decimal = Field(default=Decimal("0.95"), ge=0, le=1)
    series: tuple[FrozenSeriesPlan, ...] = Field(min_length=1)

    @field_validator("approved_at")
    @classmethod
    def approval_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("approved_at must include a timezone")
        return value

    @model_validator(mode="after")
    def valid_window_and_unique_series(self) -> "FrozenDataPlan":
        if self.historical_start_date > self.historical_end_date:
            raise ValueError("historical_start_date must not follow historical_end_date")
        if self.historical_end_date > self.reporting_as_of_date:
            raise ValueError("historical_end_date must not follow reporting_as_of_date")
        keys = [(item.source_id, item.series_id) for item in self.series]
        if len(keys) != len(set(keys)):
            raise ValueError("source_id and series_id pairs must be unique")
        return self

    def hash_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("plan_sha256", None)
        return payload

    def computed_sha256(self) -> str:
        encoded = json.dumps(
            self.hash_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class CanonicalObservation(FrozenStrictModel):
    source_id: str
    series_id: str
    series_label: str
    period: str
    value: Decimal | None
    unit: str
    observation_frequency: Literal["monthly", "quarterly", "annual"]
    update_frequency: str
    portfolio_role: Literal["outcome", "predictor", "structural_context"]
    market_role: Literal["sale", "rent", "shared"]
    eligibility_status: Literal[
        "eligible", "before_window", "after_as_of", "missing_at_source", "incomplete_period"
    ]
    raw_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_record_reference: str
    original_period: str
    original_value: str | None
    release_date: date | None = None
    available_date: date | None = None
    derivation: str | None = None
    source_periods: tuple[str, ...] = ()
    input_series_ids: tuple[str, ...] = ()


class ProcessingIssue(FrozenStrictModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    severity: Literal["warning", "error"]
    route: RecoveryRoute
    message: str
    source_id: str | None = None
    series_id: str | None = None
    period: str | None = None


class VerificationResult(FrozenStrictModel):
    status: Literal["pass", "recovery_required", "fail"]
    plan_sha256: str
    verified_snapshot_count: int
    issues: tuple[ProcessingIssue, ...]


class SeriesValidationResult(FrozenStrictModel):
    source_id: str
    series_id: str
    status: Literal["pass", "warning", "fail"]
    observation_count: int
    eligible_observation_count: int
    period_start: str | None
    period_end: str | None
    missing_periods: tuple[str, ...]
    issues: tuple[ProcessingIssue, ...]


class TransformationTrace(FrozenStrictModel):
    operation_id: str
    operation: str
    source_id: str
    output_series_id: str
    parameters: dict[str, Any]
    input_periods: tuple[str, ...]
    output_period: str | None


class AlignedDataset(FrozenStrictModel):
    market: Literal["sale", "rent"]
    periods: tuple[str, ...]
    series_ids: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]


class CrossSeriesValidationResult(FrozenStrictModel):
    status: Literal["pass", "warning", "fail"]
    common_period_start: str | None
    common_period_end: str | None
    sale_observation_count: int
    rent_observation_count: int
    issues: tuple[ProcessingIssue, ...]


class ValidatedEvidenceBundle(FrozenStrictModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_id: str
    plan_version: int
    plan_sha256: str
    reporting_as_of_date: date
    normalized_observations: tuple[CanonicalObservation, ...]
    transformed_observations: tuple[CanonicalObservation, ...]
    sale_dataset: AlignedDataset
    rent_dataset: AlignedDataset
    series_validation: tuple[SeriesValidationResult, ...]
    cross_series_validation: CrossSeriesValidationResult
    transformation_trace: tuple[TransformationTrace, ...]


class Stage3RunResult(FrozenStrictModel):
    status: Literal["success", "recovery_required", "failed"]
    completed_checkpoint: Literal[
        "none", "normalized", "series_validated", "transformed", "cross_series_validated"
    ]
    recovery_route: RecoveryRoute | None
    output_directory: str
    evidence_bundle_path: str | None
    issues: tuple[ProcessingIssue, ...]


def load_frozen_data_plan(path: str | Path) -> FrozenDataPlan:
    return FrozenDataPlan.model_validate_json(Path(path).read_text(encoding="utf-8"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
