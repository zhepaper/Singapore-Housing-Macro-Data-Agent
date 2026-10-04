from __future__ import annotations

import json

from housing_agent.report_generation.models import ReportContext


REQUIRED_NARRATIVE_HEADINGS = (
    "## Introduction",
    "## Data and Analytical Approach",
    "## Rental-Market Findings",
    "## Sale-Market Findings",
    "## Discussion",
    "## Limitations",
    "## Conclusion",
)


SYSTEM_PROMPT = """You are an applied social-science researcher writing a concise
analytical report on Singapore's private non-landed residential sale and rental
markets. Construct a coherent argument from the supplied validated evidence. The
application, not you, renders every number, date, unit, source and citation.

Return continuous academic prose under exactly these headings:
## Introduction
## Data and Analytical Approach
## Rental-Market Findings
## Sale-Market Findings
## Discussion
## Limitations
## Conclusion

Mandatory rules:
1. Do not use tables, bullet points, an executive-summary list, or an outlook section.
2. Do not discuss the agent, software, nodes, prompts, JSON, validation workflow, or code.
3. Write an Introduction of exactly two sentences: first state the research question,
   then state how sale and rental evidence will be examined separately.
4. Write Data and Analytical Approach as one short plain-language paragraph of no more
   than five sentences. Explain frequency alignment only where it matters; do not list
   percentage, percentage-point, basis-point, or absolute-change conventions.
5. Analyse rental and sale markets separately before comparing them.
6. In each findings section, start with the market outcome, examine its predictors,
   and end with a qualified synthesis.
7. Insert empirical evidence only through an exact anchor such as
   {{CLAIM:CLAIM-008}}. Use every supplied claim anchor exactly once. Never copy,
   round, calculate, or type its numerical content yourself.
8. Insert literature only through an exact anchor such as {{LIT:ReferenceId}}.
   Never invent or alter a citation.
9. Do not write any other digits, numerical values, dates, percentages, percentage
   points, basis points, calculations, author years, or numbered lists.
10. Clearly distinguish outcomes from predictors and observed evidence from possible
   economic interpretation.
11. Explain a mechanism only when supported by a supplied rationale or literature
   record. Never claim causality and never make a point forecast.
12. The Discussion should explain why sale and rental conditions may differ; it
    should not repeat every result.
13. Preserve material limitations, especially frequency mismatch, proxy limitations,
    release timing and the distinction between pipeline and completed supply.
14. The Conclusion must answer the research question without introducing new evidence.
15. Use calibrated language such as "is consistent with", "may indicate", and
    "does not establish". Do not write a generic "signals are mixed" conclusion;
    identify the relevant mechanisms and direction of evidence.
"""


def _claim_for_prompt(claim: dict[str, object]) -> dict[str, object]:
    value = float(str(claim["value"]))
    if claim.get("derivation") and "change" in str(claim["derivation"]).lower():
        direction = "increase" if value > 0 else "decrease" if value < 0 else "unchanged"
    else:
        direction = "latest validated level"
    return {
        "anchor": f"{{{{CLAIM:{claim['claim_id']}}}}}",
        "claim_id": claim["claim_id"],
        "series_id": claim["series_id"],
        "series_label": claim["series_label"],
        "market": claim["market_role"],
        "analytical_role": claim["portfolio_role"],
        "period": claim["period"],
        "validated_value": claim["value_text"],
        "unit": claim["unit"],
        "derivation": claim.get("derivation"),
        "direction": direction,
        "selection_rationale": claim.get("rationale"),
        "permitted_literature_ids": claim.get("literature_reference_ids", []),
        "quality_notes": claim.get("quality_notes", []),
    }


def build_prompt(context: ReportContext, feedback: tuple[str, ...] = ()) -> tuple[str, str]:
    payload = context.model_dump(mode="json")
    evidence = [_claim_for_prompt(item) for item in payload["claims"]]
    literature = [
        {
            **item.model_dump(mode="json"),
            "anchor": f"{{{{LIT:{item.reference_id}}}}}",
        }
        for item in context.literature_records
    ]
    human = "\n".join([
        "RESEARCH SCOPE",
        context.scope_summary,
        "",
        "RESEARCH OBJECTIVE",
        context.user_objective,
        "",
        "VALIDATED EVIDENCE CATALOG",
        json.dumps(evidence, indent=2, ensure_ascii=False),
        "",
        "APPROVED LITERATURE CATALOG",
        json.dumps(literature, indent=2, ensure_ascii=False),
        "",
        "MANDATORY DATA-QUALITY DISCLOSURES",
        json.dumps(list(context.quality_notes), indent=2, ensure_ascii=False),
        "",
        "VERIFIER FEEDBACK FROM THE PREVIOUS DRAFT",
        json.dumps(list(feedback), indent=2, ensure_ascii=False),
        "",
        "REQUIRED HEADINGS",
        "\n".join(REQUIRED_NARRATIVE_HEADINGS),
    ])
    return SYSTEM_PROMPT.strip(), human
