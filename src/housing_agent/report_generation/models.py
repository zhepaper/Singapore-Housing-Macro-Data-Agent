from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from housing_agent.processing.models import FrozenStrictModel


class SourceRecord(FrozenStrictModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=2)
    url: str | None = None
    publisher: str | None = None


class LiteratureRecord(FrozenStrictModel):
    reference_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    citation: str = Field(min_length=2)
    url: str | None = None


class ReportBrief(FrozenStrictModel):
    title: str = "Singapore Private Non-Landed Residential Market: Indicator Analysis"
    scope_summary: str = (
        "Singapore private residential sale prices and rents, using public market-level "
        "predictors and outcome benchmarks."
    )
    user_objective: str = (
        "Monitor evidence that may be informative about changes in sale prices and rents."
    )
    report_length: Literal["concise", "standard"] = "concise"
    predictor_rationales: dict[str, str] = Field(default_factory=dict)
    rationale_reference_ids: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    literature_records: tuple[LiteratureRecord, ...] = ()
    source_records: tuple[SourceRecord, ...] = ()

    @model_validator(mode="after")
    def unique_records(self) -> "ReportBrief":
        source_ids = [item.source_id for item in self.source_records]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_records must have unique source_id values")
        reference_ids = [item.reference_id for item in self.literature_records]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("literature_records must have unique reference_id values")
        known = set(reference_ids)
        unknown = {
            reference_id
            for references in self.rationale_reference_ids.values()
            for reference_id in references
            if reference_id not in known
        }
        if unknown:
            raise ValueError(
                "rationale_reference_ids contains unknown literature records: "
                + ", ".join(sorted(unknown))
            )
        return self


class EvidenceClaim(FrozenStrictModel):
    claim_id: str = Field(pattern=r"^CLAIM-[0-9]{3}$")
    source_id: str
    series_id: str
    series_label: str
    market_role: Literal["sale", "rent", "shared"]
    portfolio_role: Literal["outcome", "predictor", "structural_context"]
    period: str
    value: Decimal
    value_text: str
    unit: str
    observation_frequency: Literal["monthly", "quarterly", "annual"]
    update_frequency: str
    derivation: str | None = None
    source_periods: tuple[str, ...] = ()
    raw_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_record_reference: str
    source_title: str | None = None
    source_url: str | None = None
    rationale: str | None = None
    literature_reference_ids: tuple[str, ...] = ()
    quality_notes: tuple[str, ...] = ()


class ReportContext(FrozenStrictModel):
    prompt_version: str
    title: str
    scope_summary: str
    user_objective: str
    report_length: Literal["concise", "standard"]
    reporting_as_of_date: date
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claims: tuple[EvidenceClaim, ...]
    quality_notes: tuple[str, ...]
    literature_records: tuple[LiteratureRecord, ...] = ()
    source_records: tuple[SourceRecord, ...] = ()


class WriterOutput(FrozenStrictModel):
    narrative: str = Field(min_length=20)
    provider: str
    model: str | None = None
    prompt_version: str
    attempt: int = Field(ge=1, le=3)
    token_usage: dict[str, Any] | None = None


class ReportVerification(FrozenStrictModel):
    status: Literal["pass", "fail"]
    claims_checked: int = Field(ge=0)
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class ReportRunResult(FrozenStrictModel):
    status: Literal["success", "blocked", "failed"]
    attempts: int = Field(ge=0, le=3)
    output_directory: str
    report_path: str | None = None
    verification_path: str | None = None
    errors: tuple[str, ...] = ()
