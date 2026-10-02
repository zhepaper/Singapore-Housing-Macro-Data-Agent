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
    ]
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in sorted(change_items, key=lambda row: (row["market"], row["series_label"])):
        indicator = item["factor"].replace("_", " ")
        key = (item["market"], indicator)
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "market": item["market"],
            "indicator": indicator,
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
                f"{row['indicator']} {row['direction']}" for row in rows[:3]
            )
            return f"The validated evidence shows that {signals}. These are descriptive signals rather than causal estimates."

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
        chain = prompt | self.model | StrOutputParser()
        narrative = chain.invoke({
            "evidence": json.dumps(qualitative_context(evidence), indent=2),
            "feedback": json.dumps(feedback or []),
        })
        response_metadata = getattr(self.model, "response_metadata", {})
        return WriterResult(narrative=narrative.strip(), metadata={
            "writer": "langchain",
            "prompt_version": PROMPT_VERSION,
            "model": getattr(self.model, "model_name", type(self.model).__name__),
            "feedback_count": len(feedback or []),
            "token_usage": response_metadata.get("token_usage") if response_metadata else None,
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        })


def _format_value(value: float, unit: str) -> str:
    if unit in {"persons", "dwelling units"}:
        return f"{value:,.0f}"
    return f"{value:.3f}"


def compose_report(
    *, reporting_as_of_date: str, narrative: str, evidence: dict[str, dict[str, Any]],
    warnings: list[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        "# Singapore Private Non-Landed Housing Indicator Brief",
        "",
        f"**Information cut-off:** {reporting_as_of_date}",
        "",
        "This report presents descriptive public-data signals, not causal estimates or model forecasts.",
        "",
        "## Analysis",
        "",
        narrative.strip(),
        "",
    ]
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
            lines.extend([
                f"<!-- claim:{claim_id} -->",
                f"- **{item['series_label']}**: {value_text} {item['unit']} in {item['period']}."
                f"{source_month}{incomplete} Source: {citation}",
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
    lines.append("")
    return "\n".join(lines), ledger
