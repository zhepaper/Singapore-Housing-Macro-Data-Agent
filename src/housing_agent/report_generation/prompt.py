from __future__ import annotations

import json

from housing_agent.report_generation.models import ReportContext


REQUIRED_NARRATIVE_HEADINGS = (
    "### Executive Summary",
    "### Sale-Market Interpretation",
    "### Rental-Market Interpretation",
    "### Shared Signals",
    "### Cross-Series Interpretation",
    "### Conclusion",
)


SYSTEM_PROMPT = """You are a financial-data research analyst writing a concise report on
Singapore's private residential market. You may interpret only the supplied validated
evidence. The code, not you, renders every numerical claim.

Mandatory rules:
1. Return only the qualitative Markdown narrative under the exact required headings.
2. Do not write digits, numerical values, dates, percentages, basis points, or calculations.
3. Do not retrieve, infer, estimate, or invent facts or sources.
4. Distinguish sale-market, rental-market, and shared indicators.
5. Distinguish observed evidence from possible economic interpretation.
6. Never claim causality and never make a point forecast.
7. Use calibrated language such as "may indicate", "is consistent with", and
   "should be interpreted cautiously".
8. Discuss conflicting or insufficient signals explicitly.
9. Do not describe this analysis as a forecasting model.
10. Preserve material limitations supplied in the context.
"""


def _qualitative_claim(claim: dict[str, object]) -> dict[str, object]:
    value = float(str(claim["value"]))
    if claim.get("derivation") and "change" in str(claim["derivation"]).lower():
        direction = "increased" if value > 0 else "decreased" if value < 0 else "was unchanged"
    else:
        direction = "latest validated level available"
    return {
        "series_id": claim["series_id"],
        "series_label": claim["series_label"],
        "market_role": claim["market_role"],
        "portfolio_role": claim["portfolio_role"],
        "qualitative_signal": direction,
        "rationale": claim.get("rationale"),
        "literature_reference_ids": claim.get("literature_reference_ids", []),
        "quality_notes": claim.get("quality_notes", []),
    }


def build_prompt(context: ReportContext, feedback: tuple[str, ...] = ()) -> tuple[str, str]:
    payload = context.model_dump(mode="json")
    qualitative_evidence = [_qualitative_claim(item) for item in payload["claims"]]
    human = "\n".join([
        "RESEARCH SCOPE",
        context.scope_summary,
        "",
        "USER OBJECTIVE",
        context.user_objective,
        "",
        "QUALITATIVE EVIDENCE",
        json.dumps(qualitative_evidence, indent=2, ensure_ascii=False),
        "",
        "DATA-QUALITY NOTES",
        json.dumps(list(context.quality_notes), indent=2, ensure_ascii=False),
        "",
        "LITERATURE RECORDS",
        json.dumps(
            [item.model_dump(mode="json") for item in context.literature_records],
            indent=2,
            ensure_ascii=False,
        ),
        "",
        "VERIFIER FEEDBACK FROM THE PREVIOUS DRAFT",
        json.dumps(list(feedback), indent=2, ensure_ascii=False),
        "",
        "REQUIRED HEADINGS",
        "\n".join(REQUIRED_NARRATIVE_HEADINGS),
    ])
    return SYSTEM_PROMPT.strip(), human
