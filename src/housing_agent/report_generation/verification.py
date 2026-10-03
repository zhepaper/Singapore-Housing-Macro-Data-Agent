from __future__ import annotations

import re

from housing_agent.report_generation.composer import compose_report
from housing_agent.report_generation.models import (
    EvidenceClaim,
    ReportContext,
    ReportVerification,
)
from housing_agent.report_generation.prompt import REQUIRED_NARRATIVE_HEADINGS


PROHIBITED_PHRASES = (
    "causes",
    "caused",
    "will rise",
    "will fall",
    "predicts that",
    "guarantees",
    "forecast shows",
)


def _claim_block(report: str, claim: EvidenceClaim) -> str | None:
    marker = f"<!-- claim:{claim.claim_id} -->"
    if report.count(marker) != 1:
        return None
    remainder = report.split(marker, 1)[1]
    next_marker = remainder.find("<!-- claim:")
    next_heading = remainder.find("\n##")
    boundaries = [value for value in (next_marker, next_heading) if value >= 0]
    return remainder[: min(boundaries)] if boundaries else remainder


def verify_report(report: str, context: ReportContext) -> ReportVerification:
    errors: list[str] = []
    warnings: list[str] = []
    required_sections = (
        "## Scope and Method",
        "## Analytical Interpretation",
        "## Indicator Rationale and Literature",
        "## Validated Evidence",
        "## Data Quality and Limitations",
        "## Sources",
    )
    for heading in required_sections:
        if report.count(heading) != 1:
            errors.append(f"Missing or duplicated required report section: {heading}")
    cutoff = f"**Information cut-off:** {context.reporting_as_of_date.isoformat()}"
    if report.count(cutoff) != 1:
        errors.append("Reporting as-of date is missing or altered")

    for claim in context.claims:
        block = _claim_block(report, claim)
        if block is None:
            errors.append(f"Missing or duplicated claim marker: {claim.claim_id}")
            continue
        for expected, label in (
            (claim.value_text, "value"),
            (claim.unit, "unit"),
            (claim.period, "period"),
            (claim.source_id, "source ID"),
            (claim.observation_frequency, "observation frequency"),
            (claim.update_frequency, "update frequency"),
        ):
            if str(expected) not in block:
                errors.append(f"{claim.claim_id} has unmatched {label}")
        if claim.derivation and claim.derivation not in block:
            errors.append(f"{claim.claim_id} omits deterministic derivation")
        for source_period in claim.source_periods:
            if source_period not in block:
                errors.append(f"{claim.claim_id} omits source period {source_period}")

    analytical = ""
    if "## Analytical Interpretation" in report and "## Indicator Rationale and Literature" in report:
        analytical = report.split("## Analytical Interpretation", 1)[1].split(
            "## Indicator Rationale and Literature", 1
        )[0]
    for heading in REQUIRED_NARRATIVE_HEADINGS:
        if analytical.count(heading) != 1:
            errors.append(f"Qualitative narrative is missing or duplicates heading: {heading}")
    if re.search(r"\d", analytical):
        errors.append("Qualitative narrative contains unsupported numerical text")
    lowered = analytical.lower()
    for phrase in PROHIBITED_PHRASES:
        if phrase in lowered:
            errors.append(f"Qualitative narrative contains prohibited claim: {phrase}")

    quality = ""
    if "## Data Quality and Limitations" in report and "## Sources" in report:
        quality = report.split("## Data Quality and Limitations", 1)[1].split(
            "## Sources", 1
        )[0]
    for note in context.quality_notes:
        if note not in quality:
            errors.append(f"Report omits required quality disclosure: {note}")
    if "not a forecasting model" not in report.lower():
        errors.append("Report omits the non-forecasting disclosure")

    rationale_section = ""
    if "## Indicator Rationale and Literature" in report and "## Validated Evidence" in report:
        rationale_section = report.split("## Indicator Rationale and Literature", 1)[1].split(
            "## Validated Evidence", 1
        )[0]
    known_references = {item.reference_id for item in context.literature_records}
    for claim in context.claims:
        if claim.rationale and claim.rationale not in rationale_section:
            errors.append(f"Report omits rationale for {claim.series_id}")
        for reference_id in claim.literature_reference_ids:
            if reference_id not in known_references:
                errors.append(f"Claim uses unknown literature reference: {reference_id}")
            if reference_id not in rationale_section:
                errors.append(f"Report omits literature reference: {reference_id}")

    all_markers = set(re.findall(r"<!-- claim:(CLAIM-[0-9]{3}) -->", report))
    expected_markers = {claim.claim_id for claim in context.claims}
    for extra in sorted(all_markers - expected_markers):
        errors.append(f"Report contains unsupported claim marker: {extra}")
    if analytical and report != compose_report(context, analytical.strip()):
        errors.append(
            "Content outside the qualitative narrative differs from the deterministic report rendering"
        )
    return ReportVerification(
        status="pass" if not errors else "fail",
        claims_checked=len(context.claims),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
