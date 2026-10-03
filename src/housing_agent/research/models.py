from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _require_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("value must be an absolute HTTP or HTTPS URL")
    return value


class FactorCategory(str, Enum):
    MACROECONOMIC = "macroeconomic"
    FINANCIAL = "financial"
    DEMOGRAPHIC = "demographic"
    MARKET_LEVEL = "market_level"


class HousingSegment(str, Enum):
    PRIVATE_RESIDENTIAL = "private_residential"
    HDB = "hdb"


class MarketOutcome(str, Enum):
    SALE = "sale"
    RENT = "rent"


class EvidenceSourceType(str, Enum):
    ACADEMIC_PAPER = "academic_paper"
    OFFICIAL_REPORT = "official_report"
    INSTITUTIONAL_RESEARCH = "institutional_research"


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    UNSUPPORTED = "unsupported"


class EvidenceTemporalRole(str, Enum):
    AVAILABLE_AS_OF = "available_as_of"
    METHOD_DESIGN_ONLY = "method_design_only"


class Relevance(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class ExpectedDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    AMBIGUOUS = "ambiguous"


class MarketRole(str, Enum):
    SHARED = "shared"
    SALE_FOCUSED = "sale_focused"
    RENT_FOCUSED = "rent_focused"


class AnalyticalRole(str, Enum):
    TIMELY_PREDICTOR = "timely_predictor"
    STRUCTURAL_CONTEXT = "structural_context"


class ApprovedResearchScope(StrictModel):
    geography: str = Field(min_length=2)
    housing_segments: list[HousingSegment] = Field(min_length=1)
    markets: list[MarketOutcome] = Field(min_length=1)
    transaction_channels: list[str] = Field(min_length=1)
    excluded_channels: list[str]
    reporting_as_of_date: date
    historical_start_date: date | None
    preferred_frequencies: list[str] = Field(min_length=1)
    factor_categories: list[FactorCategory] = Field(min_length=1)
    scope_notes: list[str]

    @model_validator(mode="after")
    def unique_scope_values(self) -> "ApprovedResearchScope":
        for field_name in (
            "housing_segments",
            "markets",
            "transaction_channels",
            "excluded_channels",
            "preferred_frequencies",
            "factor_categories",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        if (
            self.historical_start_date is not None
            and self.historical_start_date > self.reporting_as_of_date
        ):
            raise ValueError("historical_start_date must not follow reporting_as_of_date")
        return self


class SearchQuery(StrictModel):
    factor_category: FactorCategory
    query: str = Field(min_length=8)
    purpose: str = Field(min_length=8)


class EvidenceSource(StrictModel):
    evidence_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=3)
    authors_or_issuer: list[str] = Field(min_length=1)
    publication_date: str | None
    url: str
    source_type: EvidenceSourceType
    singapore_specific: bool
    supported_claim: str = Field(min_length=20)
    locator: str = Field(min_length=1)
    temporal_role: EvidenceTemporalRole
    inference_notes: list[str]

    _validate_url = field_validator("url")(_require_http_url)

    @field_validator("publication_date")
    @classmethod
    def validate_publication_date(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("publication_date must use YYYY-MM-DD format") from exc
        return value


class MarketMechanism(StrictModel):
    housing_segment: HousingSegment
    market: MarketOutcome
    transaction_channels: list[str] = Field(min_length=1)
    relevance: Relevance
    explanation: str = Field(min_length=30)
    expected_direction: ExpectedDirection
    evidence_ids: list[str] = Field(min_length=1)


class DataRequirement(StrictModel):
    target_concept: str = Field(min_length=15)
    preferred_frequency: str = Field(min_length=2)
    acceptable_frequencies: list[str] = Field(min_length=1)
    preferred_unit: str = Field(min_length=1)
    likely_agencies: list[str] = Field(min_length=1)
    historical_coverage_required_from: str | None
    source_search_hints: list[str] = Field(min_length=1)
    frequency_rationale: str = Field(min_length=20)

    @field_validator("historical_coverage_required_from")
    @classmethod
    def validate_historical_start(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(
                    "historical_coverage_required_from must use YYYY-MM-DD format"
                ) from exc
        return value


class AssessmentComponent(StrictModel):
    rating: EvidenceStrength
    rationale: str = Field(min_length=20)
    evidence_ids: list[str]


class ResearchAssessment(StrictModel):
    literature_support: AssessmentComponent
    singapore_specificity: AssessmentComponent
    target_market_mechanism: AssessmentComponent
    frequency_suitability: AssessmentComponent
    non_redundancy: AssessmentComponent
    interpretability: AssessmentComponent


class PredictorCandidate(StrictModel):
    predictor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    name: str = Field(min_length=3)
    factor_category: FactorCategory
    market_role: MarketRole
    analytical_role: AnalyticalRole
    concept_definition: str = Field(min_length=20)
    mechanisms: list[MarketMechanism] = Field(min_length=1)
    evidence_sources: list[EvidenceSource] = Field(min_length=1)
    data_requirement: DataRequirement
    research_assessment: ResearchAssessment
    ranking_reason: str = Field(min_length=20)
    limitations: list[str] = Field(min_length=1)
    endogeneity_risks: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_references_exist(self) -> "PredictorCandidate":
        evidence_ids = {source.evidence_id for source in self.evidence_sources}
        if len(evidence_ids) != len(self.evidence_sources):
            raise ValueError("evidence_id values must be unique within a candidate")
        mechanism_references = {
            evidence_id
            for mechanism in self.mechanisms
            for evidence_id in mechanism.evidence_ids
        }
        assessment_references = {
            evidence_id
            for component in (
                self.research_assessment.literature_support,
                self.research_assessment.singapore_specificity,
                self.research_assessment.target_market_mechanism,
                self.research_assessment.frequency_suitability,
                self.research_assessment.non_redundancy,
                self.research_assessment.interpretability,
            )
            for evidence_id in component.evidence_ids
        }
        referenced = mechanism_references | assessment_references
        unknown = referenced - evidence_ids
        if unknown:
            raise ValueError(f"mechanisms reference unknown evidence IDs: {sorted(unknown)}")
        return self


class RejectedCandidate(StrictModel):
    name: str = Field(min_length=3)
    factor_category: FactorCategory
    rejection_reason: str = Field(min_length=20)
    source_urls: list[str]

    @field_validator("source_urls")
    @classmethod
    def validate_source_urls(cls, values: list[str]) -> list[str]:
        return [_require_http_url(value) for value in values]


class ResearchProposal(StrictModel):
    scope_summary: str = Field(min_length=30)
    search_queries: list[SearchQuery] = Field(min_length=1)
    candidates: list[PredictorCandidate] = Field(min_length=1)
    rejected_candidates: list[RejectedCandidate]
    unresolved_questions: list[str]
    research_limitations: list[str] = Field(min_length=1)


class ResearchValidationResult(StrictModel):
    automated_validation_status: Literal["pass", "fail"]
    scope_validation_status: Literal["pass", "fail"]
    evidence_validation_status: Literal["pass", "fail"]
    human_review_status: Literal["pending", "not_ready"]
    errors: list[str]
    warnings: list[str]
    candidate_counts: dict[str, int]
    covered_scope_pairs: list[str]
    candidate_scores: list["CandidateResearchScore"]


class CandidateResearchScore(StrictModel):
    predictor_id: str
    total_score: int = Field(ge=0, le=100)
    score_breakdown: dict[str, int]
    rating_adjustments: list[str]
    hard_gate_status: Literal["pass", "fail"]
    hard_gate_failures: list[str]


def migrate_legacy_predictor_candidate(value: dict) -> dict:
    """Convert a v2 candidate into the non-operational v3 schema."""
    import copy

    migrated = copy.deepcopy(value)
    requirement = migrated.get("data_requirement", {})
    legacy = requirement.pop("frequency_handling", None)
    if "frequency_rationale" not in requirement:
        messages = {
            "preserve_native_frequency": (
                "The concept should remain available at its native frequency; "
                "any later comparison view requires separate review."
            ),
            "aggregate_higher_frequency_to_quarterly": (
                "The concept is available more frequently than quarterly outcomes, "
                "but any alignment operation requires separate review."
            ),
            "other_requires_review": (
                "The source frequency and any analytical alignment operation require "
                "separate review after data discovery."
            ),
        }
        requirement["frequency_rationale"] = messages.get(
            legacy,
            "The native source frequency should be verified during data discovery "
            "before any analytical alignment is considered.",
        )
    return migrated


def load_predictor_candidate(value: dict) -> PredictorCandidate:
    return PredictorCandidate.model_validate(migrate_legacy_predictor_candidate(value))


def migrate_legacy_research_proposal(value: dict) -> dict:
    """Convert v2 SearchNode output into the non-operational v3 schema."""
    import copy

    migrated = copy.deepcopy(value)
    migrated["candidates"] = [
        migrate_legacy_predictor_candidate(candidate)
        for candidate in migrated.get("candidates", [])
    ]
    return migrated


def load_research_proposal(value: dict) -> ResearchProposal:
    return ResearchProposal.model_validate(migrate_legacy_research_proposal(value))
