from __future__ import annotations

from collections import defaultdict

from housing_agent.research.models import ResearchProposal, ResearchValidationResult


ROLE_TITLES = {
    "shared": "Shared predictors",
    "sale_focused": "Sale-focused predictors",
    "rent_focused": "Rent-focused predictors",
}


def _year(publication_date: str | None) -> str:
    return publication_date[:4] if publication_date else "n.d."


def _inline_citation(source) -> str:
    author = source.authors_or_issuer[0]
    return f"[{author} ({_year(source.publication_date)})]({source.url})"


def render_academic_research_summary(
    proposal: ResearchProposal,
    validation: ResearchValidationResult,
) -> str:
    """Render cited prose strictly from the validated structured proposal."""
    score_by_id = {
        item.predictor_id: item for item in validation.candidate_scores
    }
    candidates_by_role = defaultdict(list)
    for candidate in proposal.candidates:
        candidates_by_role[candidate.market_role.value].append(candidate)

    lines = [
        "# Predictor Research Synthesis",
        "",
        proposal.scope_summary,
        "",
        (
            "The candidates below are research proposals rather than approved production "
            "inputs. Numeric research scores are calculated deterministically from the "
            "evidence-linked assessment, and all candidates remain subject to human review."
        ),
    ]
    references: dict[str, object] = {}

    for role in ("shared", "sale_focused", "rent_focused"):
        candidates = candidates_by_role.get(role, [])
        if not candidates:
            continue
        lines.extend(["", f"## {ROLE_TITLES[role]}", ""])
        for candidate in candidates:
            score = score_by_id[candidate.predictor_id]
            source_by_id = {
                source.evidence_id: source
                for source in candidate.evidence_sources
            }
            mechanism_sentences: list[str] = []
            cited_ids: set[str] = set()
            for mechanism in candidate.mechanisms:
                mechanism_sources = [
                    source_by_id[evidence_id]
                    for evidence_id in mechanism.evidence_ids
                    if evidence_id in source_by_id
                ]
                cited_ids.update(source.evidence_id for source in mechanism_sources)
                citations = "; ".join(
                    _inline_citation(source) for source in mechanism_sources
                )
                sentence = (
                    f"For the **{mechanism.market.value}** market, "
                    f"{mechanism.explanation.rstrip('.')}"
                )
                if citations:
                    sentence += f" ({citations})."
                else:
                    sentence += "."
                mechanism_sentences.append(sentence)

            for source in candidate.evidence_sources:
                references[source.url] = source
            unused_sources = [
                source for source in candidate.evidence_sources
                if source.evidence_id not in cited_ids
            ]
            supplemental = ""
            if unused_sources:
                supplemental = " Additional context is provided by " + "; ".join(
                    _inline_citation(source) for source in unused_sources
                ) + "."
            limitations = " ".join(candidate.limitations)
            adjustment_note = ""
            if score.rating_adjustments:
                adjustment_note = (
                    " The deterministic scorer applied the following calibration: "
                    + "; ".join(score.rating_adjustments)
                    + "."
                )
            lines.append(
                f"**{candidate.name}** is classified as `{candidate.market_role.value}` "
                f"and `{candidate.analytical_role.value}` (research score: "
                f"**{score.total_score}/100**). {candidate.concept_definition} "
                + " ".join(mechanism_sentences)
                + supplemental
                + f" The principal limitations are: {limitations}"
                + adjustment_note
            )
            lines.append("")

    lines.extend(["## References", ""])
    for source in sorted(
        references.values(),
        key=lambda item: (_year(item.publication_date), item.title),
    ):
        authors = ", ".join(source.authors_or_issuer)
        lines.append(
            f"- {authors}. ({_year(source.publication_date)}). "
            f"[{source.title}]({source.url})."
        )

    return "\n".join(lines).rstrip() + "\n"
