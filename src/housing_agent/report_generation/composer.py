from __future__ import annotations

from housing_agent.report_generation.models import EvidenceClaim, ReportContext


def _claim_line(claim: EvidenceClaim) -> str:
    source = claim.source_title or claim.source_id
    if claim.source_url:
        source = f"[{source}]({claim.source_url})"
    lineage = ""
    if claim.derivation:
        inputs = ", ".join(claim.source_periods) or "recorded inputs"
        lineage = f" Derivation: `{claim.derivation}`; input period(s): {inputs}."
    return (
        f"<!-- claim:{claim.claim_id} -->\n"
        f"- **{claim.series_label}**: {claim.value_text} {claim.unit} in {claim.period}. "
        f"Frequency: {claim.observation_frequency}; update frequency: {claim.update_frequency}."
        f"{lineage} Source: {source} (`{claim.source_id}`)."
    )


def compose_report(context: ReportContext, narrative: str) -> str:
    lines = [
        f"# {context.title}",
        "",
        f"**Information cut-off:** {context.reporting_as_of_date.isoformat()}",
        "",
        "## Scope and Method",
        "",
        context.scope_summary,
        "",
        context.user_objective,
        "",
        "This report is generated only from the Stage 3 validated evidence bundle. "
        "All numerical claims below are rendered by deterministic code; the qualitative "
        "interpretation does not perform new calculations. This is an indicator-monitoring "
        "report, not a forecasting model or a causal estimate.",
        "",
        "## Analytical Interpretation",
        "",
        narrative.strip(),
        "",
        "## Indicator Rationale and Literature",
        "",
    ]
    rationale_rows: dict[tuple[str, str], EvidenceClaim] = {}
    for claim in context.claims:
        rationale_rows.setdefault((claim.source_id, claim.series_label.split(" (")[0]), claim)
    if any(item.rationale for item in rationale_rows.values()):
        lines.extend([
            "| Indicator | Market | Selection rationale | Literature support |",
            "|---|---|---|---|",
        ])
        for claim in rationale_rows.values():
            rationale = claim.rationale or "No separate predictor rationale was supplied."
            references = ", ".join(f"`{item}`" for item in claim.literature_reference_ids) or "Not supplied"
            lines.append(
                f"| {claim.series_label.split(' (')[0]} | {claim.market_role.title()} | "
                f"{rationale} | {references} |"
            )
    else:
        lines.append(
            "No separate predictor-rationale brief was supplied to Stage 4; the validated "
            "evidence and source lineage remain available below."
        )
    lines.extend([
        "",
        "## Validated Evidence",
        "",
    ])
    for market, heading in (("sale", "Sale Market"), ("rent", "Rental Market"), ("shared", "Shared Indicators")):
        lines.extend([f"### {heading}", ""])
        claims = [item for item in context.claims if item.market_role == market]
        if not claims:
            lines.extend(["No validated reportable claim is available for this category.", ""])
            continue
        for claim in claims:
            lines.extend([_claim_line(claim), ""])

    lines.extend(["## Data Quality and Limitations", ""])
    for note in context.quality_notes:
        lines.append(f"- {note}")
    claim_notes = sorted({note for claim in context.claims for note in claim.quality_notes})
    for note in claim_notes:
        lines.append(f"- {note}")
    lines.extend(["", "## Sources", ""])
    if context.source_records:
        for source in context.source_records:
            title = f"[{source.title}]({source.url})" if source.url else source.title
            publisher = f" — {source.publisher}" if source.publisher else ""
            lines.append(f"- `{source.source_id}`: {title}{publisher}")
    else:
        for source_id in sorted({claim.source_id for claim in context.claims}):
            lines.append(
                f"- `{source_id}`: source identity and raw lineage are retained in the claim ledger; "
                "no separate source-page URL was supplied to Stage 4."
            )
    if context.literature_records:
        lines.extend(["", "### Literature Used for Predictor Rationale", ""])
        for item in context.literature_records:
            citation = f"[{item.citation}]({item.url})" if item.url else item.citation
            lines.append(f"- `{item.reference_id}`: {citation}")
    lines.append("")
    return "\n".join(lines)
