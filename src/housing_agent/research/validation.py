from __future__ import annotations

from collections import Counter
from datetime import date
from urllib.parse import urlparse

from housing_agent.research.models import (
    AnalyticalRole,
    ApprovedResearchScope,
    CandidateResearchScore,
    EvidenceStrength,
    EvidenceTemporalRole,
    MarketRole,
    ResearchProposal,
    ResearchValidationResult,
)
from housing_agent.memory.models import MemorySnapshot


SCORE_WEIGHTS = {
    "literature_support": 25,
    "singapore_specificity": 20,
    "target_market_mechanism": 20,
    "frequency_suitability": 15,
    "non_redundancy": 10,
    "interpretability": 10,
}

RATING_POINTS = {
    EvidenceStrength.STRONG: {25: 25, 20: 20, 15: 15, 10: 10},
    EvidenceStrength.MEDIUM: {25: 15, 20: 12, 15: 9, 10: 6},
    EvidenceStrength.WEAK: {25: 6, 20: 5, 15: 4, 10: 2},
    EvidenceStrength.UNSUPPORTED: {25: 0, 20: 0, 15: 0, 10: 0},
}


def _normalised_url(value: object) -> str:
    parsed = urlparse(str(value))
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def _score_candidate(candidate) -> tuple[dict[str, int], int, list[str]]:
    breakdown: dict[str, int] = {}
    adjustments: list[str] = []
    for component_name, weight in SCORE_WEIGHTS.items():
        component = getattr(candidate.research_assessment, component_name)
        effective_rating = component.rating
        if (
            component_name in {"literature_support", "target_market_mechanism"}
            and component.rating is EvidenceStrength.STRONG
            and len(set(component.evidence_ids)) < 2
        ):
            effective_rating = EvidenceStrength.MEDIUM
            adjustments.append(
                f"{component_name}: strong was capped at medium because fewer than "
                "two independent evidence references were supplied"
            )
        if component_name == "singapore_specificity":
            singapore_source_count = sum(
                source.singapore_specific for source in candidate.evidence_sources
            )
            if singapore_source_count == 0:
                effective_rating = EvidenceStrength.WEAK
                adjustments.append(
                    "singapore_specificity: rating was capped at weak because no "
                    "Singapore-specific evidence source was supplied"
                )
            elif (
                singapore_source_count < len(candidate.evidence_sources)
                and component.rating is EvidenceStrength.STRONG
            ):
                effective_rating = EvidenceStrength.MEDIUM
                adjustments.append(
                    "singapore_specificity: strong was capped at medium because the "
                    "evidence set was only partly Singapore-specific"
                )
        breakdown[component_name] = RATING_POINTS[effective_rating][weight]
    return breakdown, sum(breakdown.values()), adjustments


def validate_research_proposal(
    proposal: ResearchProposal,
    scope: ApprovedResearchScope,
    *,
    searched_source_urls: set[str] | None = None,
    memory_snapshot: MemorySnapshot | None = None,
) -> ResearchValidationResult:
    scope_errors: list[str] = []
    evidence_errors: list[str] = []
    warnings: list[str] = []
    counts = Counter(candidate.factor_category.value for candidate in proposal.candidates)
    requested_categories = {category.value for category in scope.factor_categories}

    if memory_snapshot is not None and memory_snapshot.approved_scope != scope:
        scope_errors.append("Approved scope does not match compiled project memory")

    unexpected_categories = set(counts) - requested_categories
    if unexpected_categories:
        scope_errors.append(
            "Proposal contains categories outside the approved scope: "
            + ", ".join(sorted(unexpected_categories))
        )
    for category in sorted(requested_categories):
        count = counts.get(category, 0)
        if count < 1:
            scope_errors.append(
                f"No candidate was returned for requested category: {category}"
            )
        elif count > 2:
            scope_errors.append(
                f"More than two candidates were returned for category: {category}"
            )

    predictor_ids = [candidate.predictor_id for candidate in proposal.candidates]
    if len(predictor_ids) != len(set(predictor_ids)):
        scope_errors.append("predictor_id values must be unique across the proposal")

    approved_segments = {segment.value for segment in scope.housing_segments}
    approved_markets = {market.value for market in scope.markets}
    approved_channels = set(scope.transaction_channels)
    covered_pairs: set[tuple[str, str]] = set()
    searched_urls = {
        _normalised_url(url) for url in (searched_source_urls or set())
    }
    candidate_scores: list[CandidateResearchScore] = []

    for candidate in proposal.candidates:
        gate_failures: list[str] = []
        source_ids = {source.evidence_id for source in candidate.evidence_sources}
        primary_markets = {
            mechanism.market.value
            for mechanism in candidate.mechanisms
            if mechanism.relevance.value == "primary"
        }

        if candidate.market_role is MarketRole.SHARED:
            if not {"sale", "rent"}.issubset(primary_markets):
                gate_failures.append(
                    "shared market_role requires primary mechanisms for sale and rent"
                )
        elif candidate.market_role is MarketRole.SALE_FOCUSED:
            if "sale" not in primary_markets or "rent" in primary_markets:
                gate_failures.append(
                    "sale_focused market_role requires a primary sale mechanism and no "
                    "primary rent mechanism"
                )
        elif candidate.market_role is MarketRole.RENT_FOCUSED:
            if "rent" not in primary_markets or "sale" in primary_markets:
                gate_failures.append(
                    "rent_focused market_role requires a primary rent mechanism and no "
                    "primary sale mechanism"
                )

        preferred_frequency = candidate.data_requirement.preferred_frequency.lower()
        annual_frequency = any(
            marker in preferred_frequency for marker in ("annual", "yearly")
        )
        if (
            annual_frequency
            and candidate.analytical_role is AnalyticalRole.TIMELY_PREDICTOR
        ):
            gate_failures.append(
                "an annual preferred frequency cannot be labelled timely_predictor"
            )

        assessment = candidate.research_assessment
        if assessment.literature_support.rating is EvidenceStrength.UNSUPPORTED:
            gate_failures.append("literature support is unsupported")
        if not assessment.literature_support.evidence_ids:
            gate_failures.append("literature support has no evidence references")
        if assessment.target_market_mechanism.rating is EvidenceStrength.UNSUPPORTED:
            gate_failures.append("target-market mechanism is unsupported")
        if not assessment.target_market_mechanism.evidence_ids:
            gate_failures.append("target-market mechanism has no evidence references")
        if (
            assessment.singapore_specificity.rating is EvidenceStrength.STRONG
            and not any(source.singapore_specific for source in candidate.evidence_sources)
        ):
            gate_failures.append(
                "strong Singapore specificity requires Singapore-specific evidence"
            )

        for mechanism in candidate.mechanisms:
            segment = mechanism.housing_segment.value
            market = mechanism.market.value
            if segment not in approved_segments:
                scope_errors.append(
                    f"{candidate.predictor_id}: mechanism includes excluded segment "
                    f"{segment}"
                )
            if market not in approved_markets:
                scope_errors.append(
                    f"{candidate.predictor_id}: mechanism includes excluded market {market}"
                )
            unexpected_channels = set(mechanism.transaction_channels) - approved_channels
            if unexpected_channels:
                scope_errors.append(
                    f"{candidate.predictor_id}: mechanism includes channels outside the "
                    f"approved scope: {sorted(unexpected_channels)}"
                )
            if segment in approved_segments and market in approved_markets:
                covered_pairs.add((segment, market))
            missing_ids = set(mechanism.evidence_ids) - source_ids
            if missing_ids:
                evidence_errors.append(
                    f"{candidate.predictor_id}: mechanism references missing evidence IDs "
                    f"{sorted(missing_ids)}"
                )

        for source in candidate.evidence_sources:
            if (
                source.publication_date is not None
                and date.fromisoformat(source.publication_date)
                > scope.reporting_as_of_date
                and source.temporal_role is not EvidenceTemporalRole.METHOD_DESIGN_ONLY
            ):
                gate_failures.append(
                    f"post-as-of source {source.evidence_id} must be marked "
                    "method_design_only"
                )
            if searched_urls and _normalised_url(source.url) not in searched_urls:
                gate_failures.append(
                    f"evidence URL was not present in web-search source metadata: "
                    f"{source.evidence_id}"
                )

        historical_start = candidate.data_requirement.historical_coverage_required_from
        if (
            historical_start is not None
            and scope.historical_start_date is not None
            and date.fromisoformat(historical_start) > scope.historical_start_date
        ):
            warnings.append(
                f"{candidate.predictor_id}: requested source coverage starts after the "
                "scope's historical start date"
            )

        for failure in gate_failures:
            evidence_errors.append(f"{candidate.predictor_id}: hard gate failed: {failure}")

        breakdown, total, adjustments = _score_candidate(candidate)
        candidate_scores.append(
            CandidateResearchScore(
                predictor_id=candidate.predictor_id,
                total_score=total,
                score_breakdown=breakdown,
                rating_adjustments=adjustments,
                hard_gate_status="fail" if gate_failures else "pass",
                hard_gate_failures=gate_failures,
            )
        )

    required_pairs = {
        (segment.value, market.value)
        for segment in scope.housing_segments
        for market in scope.markets
    }
    missing_pairs = required_pairs - covered_pairs
    for segment, market in sorted(missing_pairs):
        scope_errors.append(
            f"Approved scope is not covered by any mechanism: {segment}/{market}"
        )

    query_categories = {query.factor_category.value for query in proposal.search_queries}
    missing_query_categories = requested_categories - query_categories
    if missing_query_categories:
        warnings.append(
            "Search-query trace is missing requested categories: "
            + ", ".join(sorted(missing_query_categories))
        )

    candidate_scores.sort(key=lambda item: (-item.total_score, item.predictor_id))
    errors = scope_errors + evidence_errors
    return ResearchValidationResult(
        automated_validation_status="pass" if not errors else "fail",
        scope_validation_status="pass" if not scope_errors else "fail",
        evidence_validation_status="pass" if not evidence_errors else "fail",
        human_review_status="pending" if not errors else "not_ready",
        errors=errors,
        warnings=warnings,
        candidate_counts=dict(sorted(counts.items())),
        covered_scope_pairs=[
            f"{segment}/{market}" for segment, market in sorted(covered_pairs)
        ],
        candidate_scores=candidate_scores,
    )
