from __future__ import annotations

import re

from housing_agent.report_generation.composer import (
    CLAIM_ANCHOR_RE,
    LITERATURE_ANCHOR_RE,
    _inline_literature,
    claim_sentence,
)
from housing_agent.report_generation.models import ReportContext, ReportVerification
from housing_agent.report_generation.prompt import REQUIRED_NARRATIVE_HEADINGS


PROHIBITED_PHRASES = (
    "directly causes",
    "directly caused",
    "was caused by",
    "will rise",
    "will fall",
    "predicts that",
    "guarantees",
    "forecast shows",
)


def _validate_raw_narrative(
    narrative: str,
    context: ReportContext,
    errors: list[str],
) -> None:
    known_claims = {item.claim_id for item in context.claims}
    anchors = CLAIM_ANCHOR_RE.findall(narrative)
    for claim_id in sorted(known_claims):
        count = anchors.count(claim_id)
        if count != 1:
            errors.append(f"Evidence anchor {claim_id} must appear exactly once; found {count}")
    for unknown in sorted(set(anchors) - known_claims):
        errors.append(f"Narrative uses unknown evidence anchor: {unknown}")

    known_literature = {item.reference_id for item in context.literature_records}
    for reference_id in LITERATURE_ANCHOR_RE.findall(narrative):
        if reference_id not in known_literature:
            errors.append(f"Narrative uses unknown literature anchor: {reference_id}")

    without_anchors = CLAIM_ANCHOR_RE.sub("", narrative)
    without_anchors = LITERATURE_ANCHOR_RE.sub("", without_anchors)
    if re.search(r"\d", without_anchors):
        errors.append("Narrative contains a number outside a deterministic evidence or literature anchor")


def verify_report(
    report: str,
    context: ReportContext,
    narrative: str | None = None,
) -> ReportVerification:
    errors: list[str] = []
    warnings: list[str] = []

    for heading in REQUIRED_NARRATIVE_HEADINGS:
        if report.count(heading) != 1:
            errors.append(f"Missing or duplicated required report section: {heading}")
    if report.count("## Data Sources") != 1:
        errors.append("Missing or duplicated Data Sources section")
    if context.literature_records and report.count("## References") != 1:
        errors.append("Missing or duplicated References section")

    cutoff = f"**Information cut-off:** {context.reporting_as_of_date.isoformat()}"
    if report.count(cutoff) != 1:
        errors.append("Reporting as-of date is missing or altered")

    for claim in context.claims:
        rendered = claim_sentence(claim)
        if report.count(rendered) != 1:
            errors.append(f"Missing, duplicated or altered deterministic evidence: {claim.claim_id}")

    analytical = report.split(cutoff, 1)[1] if cutoff in report else report
    analytical = analytical.split("## Data Sources", 1)[0]
    residual = analytical
    for claim in context.claims:
        residual = residual.replace(claim_sentence(claim), "")
    for record in context.literature_records:
        residual = residual.replace(_inline_literature(record), "")
    if re.search(r"\d", residual):
        errors.append("Analytical prose contains numerical text not rendered from the claim ledger")

    lowered = analytical.lower()
    for phrase in PROHIBITED_PHRASES:
        if phrase in lowered:
            errors.append(f"Analytical prose contains prohibited causal or forecast claim: {phrase}")
    for internal_term in ("json", "langgraph", "prompt", "claim ledger", "agent node"):
        if internal_term in lowered:
            errors.append(f"Analytical report exposes internal workflow terminology: {internal_term}")
    if "formal forecast" not in lowered and "forecasting model" not in lowered:
        errors.append("Report omits the non-forecasting disclosure")
    if "causal" not in lowered:
        errors.append("Report omits the causal-interpretation limitation")

    for source in context.source_records:
        if source.title not in report or (source.url and source.url not in report):
            errors.append(f"Report omits approved data source: {source.source_id}")
    for record in context.literature_records:
        if record.citation not in report or (record.url and record.url not in report):
            errors.append(f"Report omits approved literature record: {record.reference_id}")

    if "{{CLAIM:" in report or "{{LIT:" in report:
        errors.append("Report contains an unresolved evidence or literature anchor")
    if narrative is not None:
        _validate_raw_narrative(narrative, context, errors)

    return ReportVerification(
        status="pass" if not errors else "fail",
        claims_checked=len(context.claims),
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(warnings),
    )
