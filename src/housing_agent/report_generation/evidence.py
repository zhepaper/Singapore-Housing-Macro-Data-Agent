from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from housing_agent.processing.models import CanonicalObservation, ValidatedEvidenceBundle
from housing_agent.report_generation.models import (
    EvidenceClaim,
    ReportBrief,
    ReportContext,
)


PROMPT_VERSION = "stage4-grounded-academic-writer-v2"


def evidence_sha256(bundle: ValidatedEvidenceBundle) -> str:
    payload = json.dumps(
        bundle.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _format_decimal(value: Decimal, unit: str) -> str:
    if unit.lower() in {"persons", "units", "dwelling units"}:
        return f"{value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}"
    normalized_unit = unit.lower()
    if normalized_unit in {"percent", "year-on-year percent change"}:
        precision = Decimal("0.1")
    elif normalized_unit in {"percent per annum", "percentage points", "basis points"}:
        precision = Decimal("0.01")
    else:
        precision = Decimal("0.1")
    displayed = value.quantize(precision, rounding=ROUND_HALF_UP)
    normalized = format(displayed, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _latest_by_series(
    observations: Iterable[CanonicalObservation],
) -> list[CanonicalObservation]:
    grouped: dict[tuple[str, str], list[CanonicalObservation]] = defaultdict(list)
    for item in observations:
        if item.eligibility_status != "eligible" or item.value is None:
            continue
        if "__predictive_lag_" in item.series_id:
            continue
        grouped[(item.source_id, item.series_id)].append(item)
    latest = [
        sorted(rows, key=lambda item: item.period)[-1]
        for _, rows in sorted(grouped.items())
    ]
    quarterly_bases = {
        item.series_id.split("__quarterly_", 1)[0]
        for item in latest
        if "__quarterly_" in item.series_id
    }
    return [
        item for item in latest
        if not (
            item.observation_frequency == "monthly"
            and item.series_id in quarterly_bases
        )
    ]


def select_evidence(
    bundle: ValidatedEvidenceBundle,
    brief: ReportBrief,
) -> tuple[EvidenceClaim, ...]:
    if bundle.cross_series_validation.status == "fail":
        raise ValueError("Stage 4 cannot consume a failed cross-series validation")
    source_records = {item.source_id: item for item in brief.source_records}
    observations = _latest_by_series(
        [*bundle.normalized_observations, *bundle.transformed_observations]
    )
    claims: list[EvidenceClaim] = []
    for index, item in enumerate(
        sorted(observations, key=lambda row: (row.market_role, row.source_id, row.series_id)),
        start=1,
    ):
        assert item.value is not None
        source = source_records.get(item.source_id)
        notes: list[str] = []
        if item.release_date is None:
            notes.append("No observation-level release date was supplied; the workflow relies on the approved availability rule.")
        if item.derivation:
            notes.append("Derived deterministically from the recorded source periods.")
        claims.append(EvidenceClaim(
            claim_id=f"CLAIM-{index:03d}",
            source_id=item.source_id,
            series_id=item.series_id,
            series_label=item.series_label,
            market_role=item.market_role,
            portfolio_role=item.portfolio_role,
            period=item.period,
            value=item.value,
            value_text=_format_decimal(item.value, item.unit),
            unit=item.unit,
            observation_frequency=item.observation_frequency,
            update_frequency=item.update_frequency,
            derivation=item.derivation,
            source_periods=item.source_periods,
            raw_snapshot_sha256=item.raw_snapshot_sha256,
            raw_record_reference=item.raw_record_reference,
            source_title=source.title if source else None,
            source_url=source.url if source else None,
            rationale=(
                brief.predictor_rationales.get(item.series_id)
                or brief.predictor_rationales.get(item.source_id)
            ),
            literature_reference_ids=(
                brief.rationale_reference_ids.get(item.series_id)
                or brief.rationale_reference_ids.get(item.source_id)
                or ()
            ),
            quality_notes=tuple(notes),
        ))
    if not claims:
        raise ValueError("The validated evidence bundle contains no reportable observations")
    return tuple(claims)


def build_report_context(
    bundle: ValidatedEvidenceBundle,
    brief: ReportBrief | None = None,
) -> ReportContext:
    selected_brief = brief or ReportBrief()
    claims = select_evidence(bundle, selected_brief)
    notes = [
        f"Information is limited to data available by {bundle.reporting_as_of_date.isoformat()}.",
        "The report is descriptive and does not estimate causal effects or produce a formal forecast.",
        "Displayed values are rounded to at most three decimal places; exact decimal values remain in the claim ledger.",
    ]
    for result in bundle.series_validation:
        for issue in result.issues:
            notes.append(f"{issue.code}: {issue.message}")
    for issue in bundle.cross_series_validation.issues:
        notes.append(f"{issue.code}: {issue.message}")
    excluded_incomplete = sum(
        item.eligibility_status == "incomplete_period"
        for item in [*bundle.normalized_observations, *bundle.transformed_observations]
    )
    if excluded_incomplete:
        notes.append(
            f"{excluded_incomplete} incomplete-period observation(s) were excluded from reportable claims."
        )
    return ReportContext(
        prompt_version=PROMPT_VERSION,
        title=selected_brief.title,
        scope_summary=selected_brief.scope_summary,
        user_objective=selected_brief.user_objective,
        report_length=selected_brief.report_length,
        reporting_as_of_date=bundle.reporting_as_of_date,
        evidence_sha256=evidence_sha256(bundle),
        claims=claims,
        quality_notes=tuple(dict.fromkeys(notes)),
        literature_records=selected_brief.literature_records,
        source_records=selected_brief.source_records,
    )
