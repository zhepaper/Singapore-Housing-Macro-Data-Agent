from __future__ import annotations

from housing_agent.memory.models import MemorySnapshot
from housing_agent.onboarding.discovery_models import (
    AggregationMethod,
    ChangeMethod,
    SeriesType,
)
from housing_agent.onboarding.models import ApprovedCatalogEntry
from housing_agent.preparation.models import (
    ContractValidation,
    DataPreparationProposal,
    PreparationContract,
    PreparationValidation,
)
from housing_agent.processing.policy_registry import (
    ALLOWED_CHANGE_METHODS,
    quarterly_aggregation_allowed,
)


EXPECTED_LAGS = {
    "monthly": {"mom": 1, "qoq": 3, "yoy": 12, "period_change": 1},
    "quarterly": {"qoq": 1, "yoy": 4, "period_change": 1},
    "annual": {"yoy": 1, "period_change": 1},
}


def validate_preparation_contract(
    contract: PreparationContract,
    approved_source: ApprovedCatalogEntry,
) -> ContractValidation:
    entry = approved_source.entry
    errors: list[str] = []
    warnings: list[str] = []
    if contract.source_id != entry.source_id:
        errors.append("Contract source_id does not match the approved source profile")
    if contract.predictor_id != entry.predictor_id:
        errors.append("Contract predictor_id does not match the approved source profile")
    if contract.native_frequency != entry.native_frequency:
        errors.append("Contract native frequency does not match the approved source")
    if not any(item.startswith("memory_event:") for item in contract.decision_basis):
        errors.append("decision_basis must reference a confirmed memory event")
    if not any(item.startswith("source_profile:") for item in contract.decision_basis):
        errors.append("decision_basis must reference the verified source profile")

    comparison = contract.quarterly_comparison
    if comparison is not None:
        if entry.native_frequency != "monthly":
            errors.append("A derived quarterly comparison is only valid for monthly input")
        if comparison.aggregation_method in {
            AggregationMethod.PRESERVE,
            AggregationMethod.NOT_APPLICABLE,
        }:
            errors.append("A monthly-to-quarterly view requires last, mean, or sum")
        if not quarterly_aggregation_allowed(
            entry.series_type, comparison.aggregation_method
        ):
            if comparison.aggregation_method == AggregationMethod.SUM:
                if entry.series_type == SeriesType.RATE:
                    errors.append("Rates cannot be summed across a quarter")
                elif entry.series_type in {SeriesType.STOCK, SeriesType.INDEX}:
                    errors.append("Stock and index levels cannot be summed across a quarter")
            else:
                errors.append(
                    f"{comparison.aggregation_method.value} is incompatible with "
                    f"series_type={entry.series_type.value}"
                )

    allowed_methods = ALLOWED_CHANGE_METHODS[entry.series_type]
    for calculation in contract.change_calculations:
        if calculation.method not in allowed_methods:
            errors.append(
                f"{calculation.method.value} is incompatible with "
                f"series_type={entry.series_type.value}"
            )
        input_frequency = (
            "quarterly"
            if calculation.input_view == "quarterly_comparison"
            else entry.native_frequency
        )
        expected = EXPECTED_LAGS[input_frequency].get(calculation.horizon)
        if expected is None:
            errors.append(
                f"{calculation.horizon} is not defined for {input_frequency} data"
            )
        elif calculation.lag_periods != expected:
            errors.append(
                f"{calculation.horizon} on {input_frequency} data requires "
                f"lag_periods={expected}"
            )
        if calculation.method == ChangeMethod.BASIS_POINT and entry.series_type != SeriesType.RATE:
            errors.append("Basis-point changes require a rate series")

    if contract.predictive_alignment is not None:
        if entry.native_frequency == "annual":
            errors.append("Annual structural context cannot receive quarterly predictive lags")
        if entry.native_frequency == "monthly" and comparison is None:
            errors.append(
                "Monthly data require an approved quarterly comparison view before "
                "quarterly predictive alignment"
            )
        warnings.append(
            "Predictive alignment is exploratory and must not be described as causal."
        )
    return ContractValidation(
        source_id=contract.source_id,
        status="fail" if errors else "pass",
        errors=errors,
        warnings=warnings,
    )


def validate_preparation_proposal(
    proposal: DataPreparationProposal,
    *,
    memory: MemorySnapshot,
    approved_sources: list[ApprovedCatalogEntry],
) -> PreparationValidation:
    errors: list[str] = []
    warnings: list[str] = []
    sources = {item.entry.source_id: item for item in approved_sources}
    recommendation_ids = [item.contract.source_id for item in proposal.recommendations]
    if proposal.project_id != memory.project_id:
        errors.append("Proposal project_id does not match project memory")
    if proposal.memory_version != memory.memory_version:
        errors.append("Proposal memory_version does not match project memory")
    if len(recommendation_ids) != len(set(recommendation_ids)):
        errors.append("Preparation recommendations contain duplicate source IDs")
    missing = set(sources) - set(recommendation_ids)
    unknown = set(recommendation_ids) - set(sources)
    if missing:
        errors.append(f"Recommendations are missing approved sources: {sorted(missing)}")
    if unknown:
        errors.append(f"Recommendations contain unapproved sources: {sorted(unknown)}")
    predictor_ids = {item.predictor_id for item in memory.approved_predictors}
    validations: list[ContractValidation] = []
    for recommendation in proposal.recommendations:
        contract = recommendation.contract
        source = sources.get(contract.source_id)
        if source is None:
            continue
        if contract.predictor_id not in predictor_ids:
            validations.append(ContractValidation(
                source_id=contract.source_id,
                status="fail",
                errors=["Predictor is not in confirmed project memory"],
                warnings=[],
            ))
        else:
            contract_validation = validate_preparation_contract(contract, source)
            referenced_memory_ids = {
                item.removeprefix("memory_event:")
                for item in contract.decision_basis
                if item.startswith("memory_event:")
            }
            unknown_memory_ids = referenced_memory_ids - set(memory.source_event_ids)
            expected_source_ref = f"source_profile:{contract.source_id}"
            extra_errors = []
            if unknown_memory_ids:
                extra_errors.append(
                    f"decision_basis references unknown memory events: {sorted(unknown_memory_ids)}"
                )
            if expected_source_ref not in contract.decision_basis:
                extra_errors.append(
                    "decision_basis source profile does not match contract source_id"
                )
            if extra_errors:
                contract_validation = contract_validation.model_copy(update={
                    "status": "fail",
                    "errors": [*contract_validation.errors, *extra_errors],
                })
            validations.append(contract_validation)
    for item in validations:
        errors.extend(f"{item.source_id}: {message}" for message in item.errors)
        warnings.extend(f"{item.source_id}: {message}" for message in item.warnings)
    return PreparationValidation(
        automated_validation_status="fail" if errors else "pass",
        human_review_status="not_ready" if errors else "pending",
        contract_validations=validations,
        errors=errors,
        warnings=warnings,
    )
