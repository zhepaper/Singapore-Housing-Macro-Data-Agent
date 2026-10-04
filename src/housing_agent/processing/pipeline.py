from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from housing_agent.processing.alignment import align_market_dataset, validate_cross_series
from housing_agent.processing.integrity import verify_frozen_data_plan
from housing_agent.processing.models import (
    FrozenDataPlan,
    ProcessingIssue,
    RecoveryRoute,
    Stage3RunResult,
    ValidatedEvidenceBundle,
)
from housing_agent.processing.normalization import MappingFailure, normalize_plan_with_trace
from housing_agent.processing.persistence import (
    write_checkpoint,
    write_json,
    write_observations_csv,
)
from housing_agent.processing.transformation import TransformationFailure, transform_series
from housing_agent.processing.validation import validate_all_series


def _preferred_route(issues: list[ProcessingIssue] | tuple[ProcessingIssue, ...]) -> RecoveryRoute | None:
    for route in (
        RecoveryRoute.HARD_STOP,
        RecoveryRoute.MAPPING_RECOVERY,
        RecoveryRoute.DATA_DISCOVERY,
        RecoveryRoute.HUMAN_REVIEW,
    ):
        if any(item.route == route for item in issues):
            return route
    return None


def _stop(
    root: Path,
    *,
    status: str,
    checkpoint: str,
    issues: list[ProcessingIssue] | tuple[ProcessingIssue, ...],
) -> Stage3RunResult:
    write_json(root / "validation" / "diagnostics.json", issues)
    route = _preferred_route(issues)
    return Stage3RunResult(
        status="failed" if route == RecoveryRoute.HARD_STOP else status,
        completed_checkpoint=checkpoint,
        recovery_route=route,
        output_directory=str(root.resolve()),
        evidence_bundle_path=None,
        issues=tuple(issues),
    )


def _run_stage3(plan: FrozenDataPlan, output_directory: str | Path) -> Stage3RunResult:
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "frozen_data_plan.json", plan)

    verification = verify_frozen_data_plan(plan)
    write_json(root / "validation" / "input_verification.json", verification)
    if verification.status != "pass":
        return _stop(
            root,
            status="recovery_required",
            checkpoint="none",
            issues=verification.issues,
        )

    try:
        normalized, derivation_traces = normalize_plan_with_trace(plan)
    except MappingFailure as exc:
        issue = ProcessingIssue(
            code="MAPPING_CONTRACT_FAILED",
            severity="error",
            route=RecoveryRoute.MAPPING_RECOVERY,
            message=str(exc),
        )
        return _stop(root, status="recovery_required", checkpoint="none", issues=[issue])
    normalized_path = root / "normalized" / "observations.json"
    excluded_path = root / "normalized" / "excluded_observations.json"
    csv_path = root / "normalized" / "observations.csv"
    write_json(normalized_path, normalized)
    write_json(
        excluded_path,
        [item for item in normalized if item.eligibility_status != "eligible"],
    )
    write_observations_csv(csv_path, normalized)
    write_checkpoint(
        root, "normalized", plan.plan_sha256, [normalized_path, excluded_path, csv_path]
    )

    resolved, series_validation = validate_all_series(
        normalized, plan.series, plan.historical_end_date
    )
    series_validation_path = root / "validation" / "series_validation.json"
    warnings_path = root / "validation" / "warnings.json"
    write_json(series_validation_path, series_validation)
    series_issues = [issue for result in series_validation for issue in result.issues]
    write_json(warnings_path, [item for item in series_issues if item.severity == "warning"])
    if any(result.status == "fail" for result in series_validation):
        return _stop(
            root,
            status="recovery_required",
            checkpoint="normalized",
            issues=series_issues,
        )
    write_checkpoint(
        root, "series_validated", plan.plan_sha256, [series_validation_path, warnings_path]
    )

    grouped = defaultdict(list)
    for item in resolved:
        grouped[(item.source_id, item.series_id)].append(item)
    transformed = []
    traces = list(derivation_traces)
    try:
        for series in sorted(plan.series, key=lambda item: (item.source_id, item.series_id)):
            output, trace = transform_series(
                grouped[(series.source_id, series.series_id)], series
            )
            transformed.extend(output)
            traces.extend(trace)
    except TransformationFailure as exc:
        issue = ProcessingIssue(
            code="APPROVED_TRANSFORMATION_FAILED",
            severity="error",
            route=RecoveryRoute.HUMAN_REVIEW,
            message=str(exc),
        )
        return _stop(
            root, status="recovery_required", checkpoint="series_validated", issues=[issue]
        )

    all_processed = [*resolved, *transformed]
    native_path = root / "transformed" / "native_views.json"
    monitoring_path = root / "transformed" / "native_frequency_monitoring.json"
    context_path = root / "transformed" / "structural_context.json"
    quarterly_path = root / "transformed" / "quarterly_views.json"
    changes_path = root / "transformed" / "changes.json"
    trace_path = root / "lineage" / "transformation_trace.json"
    write_json(native_path, resolved)
    write_json(
        monitoring_path,
        [
            item for item in resolved
            if item.portfolio_role != "structural_context"
            and item.observation_frequency in {"monthly", "quarterly"}
        ],
    )
    write_json(
        context_path,
        [
            item for item in resolved
            if item.portfolio_role == "structural_context"
            or item.observation_frequency == "annual"
        ],
    )
    write_json(
        quarterly_path,
        [item for item in transformed if item.observation_frequency == "quarterly"],
    )
    write_json(
        changes_path,
        [item for item in transformed if item.derivation and "change" in item.derivation],
    )
    write_json(trace_path, traces)
    write_checkpoint(
        root,
        "transformed",
        plan.plan_sha256,
        [
            native_path,
            monitoring_path,
            context_path,
            quarterly_path,
            changes_path,
            trace_path,
        ],
    )

    try:
        sale = align_market_dataset(all_processed, "sale")
        rent = align_market_dataset(all_processed, "rent")
    except ValueError as exc:
        issue = ProcessingIssue(
            code="ALIGNMENT_DUPLICATE",
            severity="error",
            route=RecoveryRoute.HARD_STOP,
            message=str(exc),
        )
        return _stop(root, status="failed", checkpoint="transformed", issues=[issue])
    sale_path = root / "transformed" / "sale_dataset.json"
    rent_path = root / "transformed" / "rent_dataset.json"
    write_json(sale_path, sale)
    write_json(rent_path, rent)

    cross = validate_cross_series(plan, all_processed, sale, rent)
    cross_path = root / "validation" / "cross_series_validation.json"
    write_json(cross_path, cross)
    if cross.status == "fail":
        return _stop(
            root,
            status="recovery_required",
            checkpoint="transformed",
            issues=cross.issues,
        )
    write_checkpoint(
        root,
        "cross_series_validated",
        plan.plan_sha256,
        [sale_path, rent_path, cross_path],
    )

    evidence = ValidatedEvidenceBundle(
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        plan_sha256=plan.plan_sha256,
        reporting_as_of_date=plan.reporting_as_of_date,
        normalized_observations=tuple(resolved),
        transformed_observations=tuple(transformed),
        sale_dataset=sale,
        rent_dataset=rent,
        series_validation=tuple(series_validation),
        cross_series_validation=cross,
        transformation_trace=tuple(traces),
    )
    evidence_path = root / "evidence" / "validated_evidence_bundle.json"
    write_json(evidence_path, evidence)
    return Stage3RunResult(
        status="success",
        completed_checkpoint="cross_series_validated",
        recovery_route=None,
        output_directory=str(root.resolve()),
        evidence_bundle_path=str(evidence_path.resolve()),
        issues=tuple([*series_issues, *cross.issues]),
    )


def run_stage3(plan: FrozenDataPlan, output_directory: str | Path) -> Stage3RunResult:
    """Run once and convert unexpected program failures into a persisted hard stop."""
    root = Path(output_directory)
    try:
        return _run_stage3(plan, root)
    except Exception as exc:
        issue = ProcessingIssue(
            code="INTERNAL_PROCESSING_ERROR",
            severity="error",
            route=RecoveryRoute.HARD_STOP,
            message=f"{type(exc).__name__}: {exc}",
        )
        return _stop(root, status="failed", checkpoint="none", issues=[issue])
