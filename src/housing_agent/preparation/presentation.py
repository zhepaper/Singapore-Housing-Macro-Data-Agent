from __future__ import annotations

from housing_agent.onboarding.models import ApprovedCatalogEntry
from housing_agent.preparation.models import (
    DataPreparationProposal,
    PreparationReviewView,
    RawSnapshotEvidence,
    SeriesInventoryRow,
)


REVIEW_OPTIONS = [
    "Approve all recommendations",
    "Approve sources, but modify transformations",
    "Replace one or more data sources",
    "Provide my own preparation instructions",
    "Reject this proposal",
]


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _coverage(snapshot: RawSnapshotEvidence) -> str:
    if snapshot.observed_period_start and snapshot.observed_period_end:
        return f"{snapshot.observed_period_start}–{snapshot.observed_period_end}"
    return "To be confirmed from the saved snapshot"


def _transformation(recommendation) -> str:
    contract = recommendation.contract
    parts = ["preserve native"]
    if contract.quarterly_comparison:
        parts.append(
            f"quarterly {contract.quarterly_comparison.aggregation_method.value}"
        )
    changes = sorted({item.method.value for item in contract.change_calculations})
    parts.extend(changes)
    if contract.predictive_alignment:
        parts.append(f"lag {contract.predictive_alignment.lag_periods} quarter(s)")
    return "; ".join(parts)


def build_preparation_review_view(
    proposal: DataPreparationProposal,
    approved_sources: list[ApprovedCatalogEntry],
    snapshots: list[RawSnapshotEvidence],
) -> PreparationReviewView:
    source_by_id = {item.entry.source_id: item for item in approved_sources}
    snapshot_by_id = {item.source_id: item for item in snapshots}
    rows: list[SeriesInventoryRow] = []
    for recommendation in proposal.recommendations:
        contract = recommendation.contract
        source = source_by_id[contract.source_id]
        entry = source.entry
        snapshot = snapshot_by_id[contract.source_id]
        rows.append(SeriesInventoryRow(
            source_id=entry.source_id,
            predictor_id=entry.predictor_id,
            series=entry.exact_series_label or entry.dataset_title,
            market_use=recommendation.market_use_summary,
            public_source=entry.official_agency,
            source_url=entry.source_page_url,
            raw_snapshot="saved" if snapshot.status == "pass" else "failed",
            raw_snapshot_path=snapshot.snapshot_path,
            definition=entry.definition,
            unit=entry.unit,
            observation_frequency=entry.native_frequency,
            update_frequency=entry.update_frequency,
            raw_coverage=_coverage(snapshot),
            validation=snapshot.status,
            recommended_transformation=_transformation(recommendation),
        ))

    headers = [
        "Series", "Market use", "Public source", "Raw snapshot", "Definition",
        "Unit", "Observation frequency", "Update frequency", "Raw coverage",
        "Validation", "Recommended transformation",
    ]
    markdown_rows = [
        [
            row.series,
            row.market_use,
            f"[{row.public_source}]({row.source_url})",
            "✅ Saved" if row.raw_snapshot == "saved" else "❌ Failed",
            row.definition,
            row.unit,
            row.observation_frequency,
            row.update_frequency,
            row.raw_coverage,
            "✅ Pass" if row.validation == "pass" else "❌ Fail",
            row.recommended_transformation,
        ]
        for row in rows
    ]
    table = "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(_cell(item) for item in row) + " |" for row in markdown_rows),
    ])
    choices = "\n".join(f"- [ ] **{item}**" for item in REVIEW_OPTIONS)
    note = (
        "This review verifies each individual source response and proposes preparation "
        "rules. Cross-series coverage and alignment are checked only after all approved "
        "series have been retrieved."
    )
    checklist = [
        "Raw response retrieved and preserved for every series",
        "Official definition retained for every series",
        "Original unit retained for every series",
        "Observation frequency retained for every series",
        "Update frequency retained for every series",
    ]
    checklist_markdown = "\n".join(f"- [x] {item}" for item in checklist)
    markdown = "\n\n".join([
        "# Data Inventory and Preparation Review",
        table,
        "## Assignment requirements\n\n" + checklist_markdown,
        "## Recommendation\n\n" + proposal.concise_recommendation,
        "## Review decision\n\n" + choices,
        "### Your instructions\n\nDescribe any preferred source, aggregation, change method, lag, or market use in your own words.",
        "_" + note + "_",
    ])
    return PreparationReviewView(
        inventory=rows,
        concise_recommendation=proposal.concise_recommendation,
        requirements_checklist=checklist,
        review_options=REVIEW_OPTIONS,
        custom_instruction_prompt=(
            "Describe any preferred source, aggregation, change method, lag, or market use in your own words."
        ),
        important_note=note,
        markdown=markdown,
    )
