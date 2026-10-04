"""Legacy report verifier used by the catalog-specific compatibility workflow."""

from __future__ import annotations

import re
from typing import Any


PROHIBITED_CLAIMS = (
    "causes",
    "will rise",
    "will fall",
    "predicts that",
    "guarantees",
)


def verify_report(
    report: str,
    claim_ledger: list[dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    ledger_metrics = {claim["metric_id"] for claim in claim_ledger}
    evidence_metrics = set(evidence)
    for missing in sorted(evidence_metrics - ledger_metrics):
        errors.append(f"Evidence metric missing from claim ledger: {missing}")
    for unsupported in sorted(ledger_metrics - evidence_metrics):
        errors.append(f"Claim ledger contains unsupported metric: {unsupported}")
    for claim in claim_ledger:
        marker = f"<!-- claim:{claim['claim_id']} -->"
        if report.count(marker) != 1:
            errors.append(f"Missing claim marker: {claim['claim_id']}")
            continue
        after_marker = report.split(marker, 1)[1].split("\n", 2)[1]
        for expected, label in (
            (claim["value_text"], "value"),
            (claim["unit"], "unit"),
            (claim["period"], "period"),
            (claim["source_url"], "source URL"),
        ):
            if str(expected) not in after_marker:
                errors.append(f"{claim['claim_id']} has unmatched {label}")
        if claim["completeness"] == "incomplete" and "Incomplete quarter" not in after_marker:
            errors.append(f"{claim['claim_id']} omits incomplete-quarter disclosure")

    analysis = ""
    if "## Analysis" in report and "## Validated evidence" in report:
        analysis = report.split("## Analysis", 1)[1].split("## Validated evidence", 1)[0]
    if re.search(r"\d", analysis):
        errors.append("Writer narrative contains unsupported numeric text")
    for heading in ("### Shared supply", "### Rental market", "### Sale market"):
        if heading not in analysis:
            errors.append(f"Writer narrative is missing required heading: {heading}")
    lowered = analysis.lower()
    for phrase in PROHIBITED_CLAIMS:
        if phrase in lowered:
            errors.append(f"Writer narrative contains prohibited claim: {phrase}")

    employment_present = any(
        item["source_id"] == "non_resident_employment_change" for item in evidence.values()
    )
    if employment_present and "Employment flow, not population stock." not in report:
        errors.append("Employment/population distinction is missing")

    allowed_urls = {claim["source_url"] for claim in claim_ledger}
    evidence_section = report.split("## Validated evidence", 1)[-1].split("## Limitations", 1)[0]
    evidence_lines = evidence_section.splitlines()
    for index, line in enumerate(evidence_lines):
        if line.startswith("- ") and re.search(r"\d", line):
            previous = evidence_lines[index - 1] if index else ""
            if not re.fullmatch(r"<!-- claim:claim-\d{3} -->", previous.strip()):
                errors.append("Quantitative evidence statement has no claim-ledger marker")
    linked_urls = set(re.findall(r"\[[^\]]+\]\((https://[^)]+)\)", evidence_section))
    for unsupported_url in sorted(linked_urls - allowed_urls):
        errors.append(f"Unsupported citation URL: {unsupported_url}")

    def section(name: str, next_name: str | None) -> str:
        start = f"### {name}"
        if start not in analysis:
            return ""
        content = analysis.split(start, 1)[1]
        if next_name and f"### {next_name}" in content:
            content = content.split(f"### {next_name}", 1)[0]
        return content.lower()

    rental_text = section("Rental market", "Sale market")
    sale_text = section("Sale market", None)
    for phrase in ("financing conditions", "sora", "sale market benchmark", "real gdp"):
        if phrase in rental_text:
            errors.append(f"Rental section contains a sale-specific mechanism: {phrase}")
    for phrase in ("vacancy", "non-resident employment", "rental demand", "rent market benchmark"):
        if phrase in sale_text:
            errors.append(f"Sale section contains a rent-specific mechanism: {phrase}")

    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "claims_checked": len(claim_ledger),
    }
