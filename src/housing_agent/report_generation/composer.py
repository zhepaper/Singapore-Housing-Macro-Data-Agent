from __future__ import annotations

import re

from housing_agent.report_generation.models import EvidenceClaim, LiteratureRecord, ReportContext


CLAIM_ANCHOR_RE = re.compile(r"\{\{CLAIM:(CLAIM-[0-9]{3})\}\}")
LITERATURE_ANCHOR_RE = re.compile(r"\{\{LIT:([A-Za-z][A-Za-z0-9_-]*)\}\}")


def _base_label(claim: EvidenceClaim) -> str:
    return claim.series_label.split(" (", 1)[0]


def _absolute_text(claim: EvidenceClaim) -> str:
    if claim.value >= 0:
        return claim.value_text
    return claim.value_text.lstrip("-")


def _direction(claim: EvidenceClaim) -> str:
    return "increased" if claim.value > 0 else "decreased" if claim.value < 0 else "was unchanged"


def _display_period(period: str) -> str:
    quarter = re.fullmatch(r"([0-9]{4})-Q([1-4])", period)
    if quarter:
        return f"{quarter.group(1)} Q{quarter.group(2)}"
    month = re.fullmatch(r"([0-9]{4})-([0-9]{2})", period)
    if month:
        names = (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        )
        return f"{names[int(month.group(2)) - 1]} {month.group(1)}"
    return period


def _value_and_unit(value_text: str, unit: str) -> str:
    normalized = unit.lower()
    if normalized == "percent":
        return f"{value_text}%"
    if normalized == "percent per annum":
        return f"{value_text}% per annum"
    if normalized == "year-on-year percent change":
        return f"{value_text}% year on year"
    if normalized.startswith("index;"):
        base = unit.split(";", 1)[1].strip().replace("-", " ").replace("=", " = ")
        return f"{value_text} index points ({base})"
    return f"{value_text} {unit}"


def _horizon(claim: EvidenceClaim) -> str | None:
    identifier = claim.series_id.lower()
    if "__qoq_" in identifier:
        return "quarter on quarter"
    if "__yoy_" in identifier:
        return "year on year"
    return None


def claim_sentence(claim: EvidenceClaim) -> str:
    """Render an immutable, reader-facing empirical sentence for one claim."""

    label = _base_label(claim)
    horizon = _horizon(claim)
    metadata = (
        f"<!-- claim:{claim.claim_id}; source:{claim.source_id}; "
        f"frequency:{claim.observation_frequency}; update:{claim.update_frequency} -->"
    )
    period = _display_period(claim.period)
    value_and_unit = _value_and_unit(_absolute_text(claim), claim.unit)
    if horizon:
        if claim.series_id.startswith("real_gdp_growth__qoq_"):
            visible = (
                f"The year-on-year real GDP growth rate {_direction(claim)} by "
                f"{value_and_unit} relative to the preceding quarter in {period}."
            )
        else:
            visible = (
                f"{label} {_direction(claim)} by {value_and_unit} "
                f"{horizon} in {period}."
            )
    elif claim.series_id == "non_resident_employment_change":
        visible = (
            f"Non-resident employment increased by "
            f"{_value_and_unit(claim.value_text, claim.unit)} in {period}."
        )
    elif claim.series_id == "real_gdp_growth":
        visible = (
            f"Real GDP growth was {_value_and_unit(claim.value_text, claim.unit)} "
            f"in {period}."
        )
    elif claim.series_id.endswith("__quarterly_last"):
        visible = (
            f"The quarter-end {label} was "
            f"{_value_and_unit(claim.value_text, claim.unit)} in {period}."
        )
    else:
        visible = (
            f"{label} stood at {_value_and_unit(claim.value_text, claim.unit)} "
            f"in {period}."
        )
    return f"{metadata} {visible}"


def _inline_literature(record: LiteratureRecord) -> str:
    match = re.match(r"^(.*?\([0-9]{4}\))\.", record.citation)
    label = match.group(1) if match else record.citation
    return f"[{label}]({record.url})" if record.url else label


def render_anchors(context: ReportContext, narrative: str) -> str:
    claims = {item.claim_id: item for item in context.claims}
    literature = {item.reference_id: item for item in context.literature_records}

    def claim_replacement(match: re.Match[str]) -> str:
        claim = claims.get(match.group(1))
        return claim_sentence(claim) if claim else match.group(0)

    def literature_replacement(match: re.Match[str]) -> str:
        record = literature.get(match.group(1))
        return _inline_literature(record) if record else match.group(0)

    rendered = CLAIM_ANCHOR_RE.sub(claim_replacement, narrative)
    return LITERATURE_ANCHOR_RE.sub(literature_replacement, rendered)


def _source_and_reference_sections(context: ReportContext) -> list[str]:
    lines = ["## Data Sources", ""]
    for source in context.source_records:
        title = f"[{source.title}]({source.url})" if source.url else source.title
        publisher = f", {source.publisher}" if source.publisher else ""
        lines.append(f"- {title}{publisher}.")
    if not context.source_records:
        for source_id in sorted({claim.source_id for claim in context.claims}):
            lines.append(f"- {source_id} (full provenance retained in the accompanying evidence files).")
    if context.literature_records:
        lines.extend(["", "## References", ""])
        for item in context.literature_records:
            citation = f"[{item.citation}]({item.url})" if item.url else item.citation
            lines.append(f"- {citation}")
    return lines


def compose_report(context: ReportContext, narrative: str) -> str:
    lines = [
        f"# {context.title}",
        "",
        f"**Information cut-off:** {context.reporting_as_of_date.isoformat()}",
        "",
        render_anchors(context, narrative.strip()),
        "",
        *_source_and_reference_sections(context),
        "",
    ]
    return "\n".join(lines)
