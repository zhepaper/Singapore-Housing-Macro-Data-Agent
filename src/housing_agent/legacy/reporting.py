"""Legacy report composer used by the catalog-specific compatibility workflow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


PROMPT_VERSION = "evidence-writer-v1"


@dataclass(frozen=True)
class WriterResult:
    narrative: str
    metadata: dict[str, Any]


def _direction(value: float) -> str:
    if value > 0:
        return "increased"
    if value < 0:
        return "decreased"
    return "was unchanged"


def qualitative_context(evidence: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    change_items = [
        item for item in evidence.values()
        if any(token in item["metric_id"] for token in ("qoq", "yoy", "previous_quarter"))
        or item["source_id"] == "non_resident_employment_change"
    ]
    output: list[dict[str, Any]] = []
    indicator_names = {
        "private_residential_pipeline_supply": "the private non-landed supply pipeline",
        "non_resident_rental_demand": "the non-resident demand signal",
        "private_residential_vacancy_rate": "the private non-landed vacancy rate",
        "financing_conditions": "the SORA financing-rate proxy",
        "real_gdp_growth": "official year-on-year real GDP growth",
        "sale_market_benchmark": "the private non-landed sale-price benchmark",
        "rent_market_benchmark": "the private non-landed rental benchmark",
    }
    for item in sorted(change_items, key=lambda row: (row["market"], row["metric_id"])):
        metric_id = item["metric_id"]
        if "yoy" in metric_id:
            horizon = "year on year"
        elif "qoq" in metric_id:
            horizon = "quarter on quarter"
        elif "previous_quarter" in metric_id:
            horizon = "relative to the previous quarter"
        else:
            horizon = "in the latest reported quarter"
        output.append({
            "market": item["market"],
            "indicator": indicator_names.get(item["factor"], item["factor"].replace("_", " ")),
            "horizon": horizon,
            "direction": _direction(float(item["value"])),
            "mechanism": item["mechanism"],
            "limitations": item["limitations"],
            "incomplete": item["completeness"] != "complete",
        })
    return output


class DeterministicWriter:
    def write(
        self, evidence: dict[str, dict[str, Any]], *, feedback: list[str] | None = None
    ) -> WriterResult:
        context = qualitative_context(evidence)
        by_market = {
            market: [item for item in context if item["market"] == market]
            for market in ("shared", "rent", "sale")
        }

        def sentence(market: str, fallback: str) -> str:
            rows = by_market[market]
            if not rows:
                return fallback
            signals = "; ".join(
                f"{row['indicator']} {row['direction']} {row['horizon']}"
                f"{' using an incomplete quarter' if row['incomplete'] else ''}"
                for row in rows
            )
            return (
                f"The validated evidence shows that {signals}. The associated mechanisms "
                "and lags are hypotheses from the indicator-selection framework, not causal estimates."
            )

        narrative = "\n\n".join([
            "### Shared supply\n\n" + sentence(
                "shared", "The shared supply evidence is currently insufficient for interpretation."
            ),
            "### Rental market\n\n" + sentence(
                "rent", "The rental evidence is currently insufficient for interpretation."
            ),
            "### Sale market\n\n" + sentence(
                "sale", "The sale evidence is currently insufficient for interpretation."
            ),
        ])
        return WriterResult(narrative=narrative, metadata={
            "writer": "deterministic",
            "prompt_version": PROMPT_VERSION,
            "model": None,
            "feedback_count": len(feedback or []),
            "token_usage": None,
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        })


class LangChainWriter:
    def __init__(self, model: Any) -> None:
        self.model = model

    def write(
        self, evidence: dict[str, dict[str, Any]], *, feedback: list[str] | None = None
    ) -> WriterResult:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You write a concise analytical narrative for Singapore's private non-landed "
                "housing market. Use only the supplied qualitative evidence. Do not include digits, "
                "numeric values, causal claims, or forecasts. Keep the headings exactly as: "
                "Shared supply, Rental market, Sale market. Distinguish employment flow from "
                "population stock and disclose incomplete evidence."
            )),
            ("human", "Evidence:\n{evidence}\n\nVerifier feedback:\n{feedback}"),
        ])
        prompt_value = prompt.invoke({
            "evidence": json.dumps(qualitative_context(evidence), indent=2),
            "feedback": json.dumps(feedback or []),
        })
        response = self.model.invoke(prompt_value)
        narrative = StrOutputParser().invoke(response)
        response_metadata = getattr(response, "response_metadata", {}) or {}
        token_usage = getattr(response, "usage_metadata", None)
        if token_usage is None:
            token_usage = response_metadata.get("token_usage")
        return WriterResult(narrative=narrative.strip(), metadata={
            "writer": "langchain",
            "prompt_version": PROMPT_VERSION,
            "model": getattr(self.model, "model_name", type(self.model).__name__),
            "feedback_count": len(feedback or []),
            "token_usage": token_usage,
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        })


def _format_value(value: float, unit: str) -> str:
    if unit in {"persons", "dwelling units"}:
        return f"{value:,.0f}"
    return f"{value:.3f}"


def _freshness_label(status: str) -> str:
    return {
        "current": "current",
        "not_yet_released": "current; next observation not yet due",
        "stale": "stale",
        "unavailable": "unavailable",
    }.get(status, status.replace("_", " "))


def compose_report(
    *, reporting_as_of_date: str, narrative: str, evidence: dict[str, dict[str, Any]],
    warnings: list[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        "# Singapore Private Non-Landed Housing Indicator Brief",
        "",
        f"**Information cut-off:** {reporting_as_of_date}",
        "",
        "## Scope",
        "",
        "This report monitors Singapore's private non-landed residential sale and rental markets. "
        "It presents descriptive public-data signals, not causal estimates or model forecasts. "
        "The sale and rental indices are outcome benchmarks; the remaining series are candidate predictors.",
        "",
        "The workflow preserves mixed frequencies: annual population is not interpolated, quarterly series "
        "remain quarterly, and monthly SORA is represented by the last available month-end observation in each quarter.",
        "",
        "## Indicator definitions and mechanisms",
        "",
        "| Indicator | Market | Definition | Observation / update frequency | Mechanism and potential lag |",
        "|---|---|---|---|---|",
    ]
    source_rows: dict[str, dict[str, Any]] = {}
    for item in evidence.values():
        source_rows.setdefault(item["source_id"], item)
    indicator_names = {
        "ura_non_landed_price_index": "URA non-landed price index",
        "ura_non_landed_rental_index": "URA non-landed rental index",
        "private_residential_pipeline_supply": "Private non-landed pipeline supply",
        "non_resident_population": "Non-resident population",
        "non_resident_employment_change": "Non-resident employment change",
        "private_non_landed_vacancy_rate": "Private non-landed vacancy rate",
        "three_month_compounded_sora": "Three-month Compounded SORA",
        "real_gdp_growth": "Real GDP growth",
    }
    for item in sorted(source_rows.values(), key=lambda row: (row["market"], row["factor"])):
        indicator = indicator_names.get(
            item["source_id"], item["factor"].replace("_", " ").title()
        )
        observation_frequency = item["observation_frequency"].replace("_", " ")
        lines.append(
            f"| **{indicator}** (`{item['series_identifier']}`) | {item['market'].title()} | "
            f"{item['definition']} | {observation_frequency} / {item['update_frequency']} | "
            f"{item['mechanism']} {item['potential_lag']} |"
        )
    lines.extend([
        "",
        "",
        "## Analysis",
        "",
        narrative.strip(),
        "",
        "## Data processing and reliability",
        "",
        "Official responses are preserved before parsing and tied to checksums. Exact series labels are selected, "
        "periods and units are normalized, the information cut-off is applied, and deterministic formulas produce "
        "changes and ratios. Validation checks required coverage, uniqueness, units, period formats, freshness, "
        "formula lineage, and zero denominators before any report is written.",
        "",
        "Most data.gov.sg endpoints expose current-vintage histories rather than archived releases. Consequently, "
        "period cut-offs are enforced, but historical point-in-time availability remains unverified where an official "
        "release date or archived vintage is unavailable. The configured MOM final report is separately checked using "
        "its published release date.",
        "",
    ])
    if warnings:
        lines.extend(["## Operational notes", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    lines.extend(["## Validated evidence", ""])
    ledger: list[dict[str, Any]] = []
    headings = [("shared", "Shared"), ("rent", "Rent"), ("sale", "Sale")]
    for market, label in headings:
        lines.extend([f"### {label}", ""])
        rows = sorted(
            (item for item in evidence.values() if item["market"] == market),
            key=lambda item: item["series_label"],
        )
        for item in rows:
            claim_id = f"claim-{len(ledger) + 1:03d}"
            value_text = _format_value(float(item["value"]), item["unit"])
            incomplete = " Incomplete quarter." if item["completeness"] == "incomplete" else ""
            source_month = (
                f" Source observation: {item['source_observation_period']}."
                if item.get("source_observation_period") else ""
            )
            citation = f"[{item['source_id']}]({item['source_page_url']})"
            lineage = ""
            if item.get("derivation"):
                input_periods = ", ".join(item.get("source_periods", []))
                lineage = f" Formula: `{item['derivation']}`; input period(s): {input_periods}."
            lines.extend([
                f"<!-- claim:{claim_id} -->",
                f"- **{item['series_label']}**: {value_text} {item['unit']} in {item['period']}."
                f"{source_month}{incomplete}{lineage} Freshness: "
                f"{_freshness_label(item['freshness_status'])}. "
                f"Source: {citation}",
            ])
            ledger.append({
                "claim_id": claim_id,
                "metric_id": item["metric_id"],
                "value_text": value_text,
                "unit": item["unit"],
                "period": item["period"],
                "source_url": item["source_page_url"],
                "completeness": item["completeness"],
            })
        lines.append("")

    limitations = sorted({
        limitation
        for item in evidence.values()
        for limitation in item["limitations"]
    })
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in limitations)
    point_in_time_notes = sorted({
        item["point_in_time_availability"] for item in evidence.values()
    })
    lines.extend(f"- {note}" for note in point_in_time_notes)
    lines.append("")
    return "\n".join(lines), ledger
