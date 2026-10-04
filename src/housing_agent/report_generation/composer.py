from __future__ import annotations

import re

from housing_agent.report_generation.models import EvidenceClaim, LiteratureRecord, ReportContext


CLAIM_ANCHOR_RE = re.compile(r"\{\{CLAIM:(CLAIM-[0-9]{3})\}\}")
LITERATURE_ANCHOR_RE = re.compile(r"\{\{LIT:([A-Za-z][A-Za-z0-9_-]*)\}\}")


def _base_label(claim: EvidenceClaim) -> str:
    return claim.series_label.split(" (", 1)[0]


def _reader_label(claim: EvidenceClaim) -> str:
    labels = {
        "ura_non_landed_rental_index": "the private non-landed rental index",
        "ura_non_landed_price_index": "the private non-landed price index",
        "private_non_landed_vacancy_rate": "the private non-landed vacancy rate",
        "non_resident_population": "the non-resident population",
        "non_resident_employment_change": "non-resident employment",
        "real_gdp_growth": "the year-on-year real GDP growth rate",
        "real_gdp_qoq_growth": "real GDP",
        "three_month_compounded_sora": "three-month Compounded SORA",
        "private_residential_pipeline_supply": "the private non-landed residential pipeline",
    }
    base_id = claim.series_id.split("__", 1)[0]
    return labels.get(base_id, _base_label(claim).lower())


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
    if normalized == "seasonally adjusted quarter-on-quarter percent change":
        return f"{value_text}% quarter on quarter on a seasonally adjusted basis"
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

    label = _reader_label(claim)
    horizon = _horizon(claim)
    period = _display_period(claim.period)
    value_and_unit = _value_and_unit(_absolute_text(claim), claim.unit)
    if horizon:
        if claim.series_id.startswith("real_gdp_growth__qoq_"):
            visible = (
                f"Compared with the preceding quarter, the year-on-year real GDP growth "
                f"rate was {value_and_unit} {'higher' if claim.value > 0 else 'lower'} "
                f"in {period}."
            )
        else:
            comparison = "the previous quarter" if horizon == "quarter on quarter" else "a year earlier"
            visible = (
                f"Compared with {comparison}, {label} was {value_and_unit} "
                f"{'higher' if claim.value > 0 else 'lower' if claim.value < 0 else 'unchanged'} "
                f"in {period}."
            )
    elif claim.series_id == "non_resident_employment_change":
        visible = (
            f"Non-resident employment increased by {claim.value_text} in {period}."
        )
    elif claim.series_id == "real_gdp_growth":
        visible = (
            f"Real GDP growth was {_value_and_unit(claim.value_text, claim.unit)} "
            f"in {period}."
        )
    elif claim.series_id == "real_gdp_qoq_growth":
        visible = (
            f"Real GDP increased by {_value_and_unit(claim.value_text, claim.unit)} "
            f"in {period}."
        )
    elif claim.series_id.endswith("__quarterly_last"):
        visible = (
            f"At the end of {period}, {label} was "
            f"{_value_and_unit(claim.value_text, claim.unit)} in {period}."
        )
        visible = visible.replace(f" in {period}.", ".")
    elif claim.source_id in {"ura_non_landed_rental_index", "ura_non_landed_price_index"}:
        visible = (
            f"In {period}, {label} was {claim.value_text}, with its level in "
            f"the first quarter of 2009 set to 100."
        )
    elif claim.series_id == "non_resident_population":
        visible = f"The non-resident population was {claim.value_text} in {period}."
    else:
        visible = (
            f"In {period}, {label} was {_value_and_unit(claim.value_text, claim.unit)} "
            f"in {period}."
        )
        visible = visible.replace(f" in {period}.", ".")
    return visible


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
