from __future__ import annotations

from housing_agent.memory.models import MemorySnapshot
from housing_agent.processing.models import FrozenDataPlan
from housing_agent.report_generation.models import ReportBrief


def report_brief_from_memory(
    memory: MemorySnapshot,
    *,
    plan: FrozenDataPlan | None = None,
    base: ReportBrief | None = None,
) -> ReportBrief:
    """Carry confirmed user context forward without treating memory as numeric evidence."""
    existing = base or ReportBrief()
    approved = {item.predictor_id: item for item in memory.approved_predictors}
    rationales = {
        predictor_id: " ".join(item.selection_rationale)
        for predictor_id, item in approved.items()
    }
    if plan is not None:
        for series in plan.series:
            predictor_id = series.preparation_contract.predictor_id
            if predictor_id in rationales:
                rationales[series.source_id] = rationales[predictor_id]
                rationales[series.series_id] = rationales[predictor_id]
    rationales.update(existing.predictor_rationales)
    scope = memory.approved_scope
    segments = ", ".join(item.value.replace("_", " ") for item in scope.housing_segments)
    markets = " and ".join(item.value for item in scope.markets)
    scope_notes = " ".join(scope.scope_notes)
    scope_summary = (
        f"{scope.geography} {segments}, covering {markets}. {scope_notes}"
    ).strip()
    objective = (
        "Monitor the human-approved predictors as potentially informative evidence for "
        f"the confirmed {markets} outcomes."
    )
    return existing.model_copy(update={
        "scope_summary": scope_summary,
        "user_objective": objective,
        "report_length": (
            "concise" if memory.reporting_preferences.concise_academic_style else "standard"
        ),
        "predictor_rationales": rationales,
    })
