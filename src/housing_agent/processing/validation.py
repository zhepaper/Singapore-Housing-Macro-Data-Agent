from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

from housing_agent.processing.models import (
    CanonicalObservation,
    FrozenSeriesPlan,
    ProcessingIssue,
    RecoveryRoute,
    SeriesValidationResult,
)


def _ordinal(period: str, frequency: str) -> int:
    if frequency == "annual":
        return int(period)
    if frequency == "quarterly":
        year, quarter = period.split("-Q")
        return int(year) * 4 + int(quarter) - 1
    year, month = period.split("-")
    return int(year) * 12 + int(month) - 1


def _period_from_ordinal(value: int, frequency: str) -> str:
    if frequency == "annual":
        return str(value)
    divisor = 4 if frequency == "quarterly" else 12
    year, remainder = divmod(value, divisor)
    return f"{year}-Q{remainder + 1}" if frequency == "quarterly" else f"{year}-{remainder + 1:02d}"


def validate_series(
    observations: Iterable[CanonicalObservation],
    series: FrozenSeriesPlan,
    reporting_period_end: date | None = None,
) -> tuple[list[CanonicalObservation], SeriesValidationResult]:
    rows = list(observations)
    issues: list[ProcessingIssue] = []
    resolved: list[CanonicalObservation] = []
    by_period: dict[str, list[CanonicalObservation]] = defaultdict(list)
    for item in rows:
        by_period[item.period].append(item)

    for period, duplicates in sorted(by_period.items()):
        if len(duplicates) == 1:
            resolved.append(duplicates[0])
            continue
        if series.duplicate_policy == "latest_release" and all(
            item.release_date is not None for item in duplicates
        ):
            resolved.append(max(duplicates, key=lambda item: item.release_date))
            issues.append(ProcessingIssue(
                code="DUPLICATE_REVISION_RESOLVED",
                severity="warning",
                route=RecoveryRoute.HUMAN_REVIEW,
                message="Duplicate period resolved using the approved latest-release policy.",
                source_id=series.source_id,
                series_id=series.series_id,
                period=period,
            ))
        else:
            issues.append(ProcessingIssue(
                code="UNEXPLAINED_DUPLICATE",
                severity="error",
                route=RecoveryRoute.HARD_STOP,
                message="The same period has multiple values without an applicable revision policy.",
                source_id=series.source_id,
                series_id=series.series_id,
                period=period,
            ))

    resolved.sort(key=lambda item: item.period)
    eligible = [item for item in resolved if item.eligibility_status == "eligible"]
    ordinals = sorted(_ordinal(item.period, item.observation_frequency) for item in eligible)
    missing: list[str] = []
    if ordinals:
        observed = set(ordinals)
        missing = [
            _period_from_ordinal(value, series.observation_frequency)
            for value in range(ordinals[0], ordinals[-1] + 1)
            if value not in observed
        ]
    if missing:
        issues.append(ProcessingIssue(
            code="CALENDAR_GAPS",
            severity="warning",
            route=RecoveryRoute.HUMAN_REVIEW,
            message=f"Series has {len(missing)} missing calendar period(s).",
            source_id=series.source_id,
            series_id=series.series_id,
        ))
    if not eligible:
        issues.append(ProcessingIssue(
            code="NO_ELIGIBLE_OBSERVATIONS",
            severity="error",
            route=RecoveryRoute.HUMAN_REVIEW,
            message="Series has no observations eligible under the frozen as-of window.",
            source_id=series.source_id,
            series_id=series.series_id,
        ))
    if len(resolved) < series.minimum_observations:
        issues.append(ProcessingIssue(
            code="INSUFFICIENT_SERIES_OBSERVATIONS",
            severity="error",
            route=RecoveryRoute.HUMAN_REVIEW,
            message=(
                f"Series has {len(resolved)} observations; the approved minimum is "
                f"{series.minimum_observations}."
            ),
            source_id=series.source_id,
            series_id=series.series_id,
        ))
    if reporting_period_end is not None and eligible:
        if series.observation_frequency == "annual":
            expected_period = str(reporting_period_end.year)
        elif series.observation_frequency == "quarterly":
            expected_period = f"{reporting_period_end.year}-Q{(reporting_period_end.month - 1) // 3 + 1}"
        else:
            expected_period = f"{reporting_period_end.year}-{reporting_period_end.month:02d}"
        staleness = _ordinal(expected_period, series.observation_frequency) - max(
            _ordinal(item.period, item.observation_frequency) for item in eligible
        )
        if staleness > series.max_staleness_periods:
            issues.append(ProcessingIssue(
                code="STALE_SERIES",
                severity="warning",
                route=RecoveryRoute.HUMAN_REVIEW,
                message=(
                    f"Latest eligible observation is {staleness} periods behind the "
                    f"reporting window; approved tolerance is {series.max_staleness_periods}."
                ),
                source_id=series.source_id,
                series_id=series.series_id,
            ))
    missing_values = sum(item.value is None for item in resolved)
    if missing_values:
        issues.append(ProcessingIssue(
            code="MISSING_VALUES_PRESERVED",
            severity="warning",
            route=RecoveryRoute.HUMAN_REVIEW,
            message=f"{missing_values} source missing value(s) were preserved as null.",
            source_id=series.source_id,
            series_id=series.series_id,
        ))
    status = (
        "fail" if any(item.severity == "error" for item in issues)
        else "warning" if issues else "pass"
    )
    periods = [item.period for item in resolved]
    return resolved, SeriesValidationResult(
        source_id=series.source_id,
        series_id=series.series_id,
        status=status,
        observation_count=len(resolved),
        eligible_observation_count=len(eligible),
        period_start=min(periods) if periods else None,
        period_end=max(periods) if periods else None,
        missing_periods=tuple(missing),
        issues=tuple(issues),
    )


def validate_all_series(
    observations: Iterable[CanonicalObservation],
    series_plans: Iterable[FrozenSeriesPlan],
    reporting_period_end: date | None = None,
) -> tuple[list[CanonicalObservation], list[SeriesValidationResult]]:
    grouped: dict[tuple[str, str], list[CanonicalObservation]] = defaultdict(list)
    for item in observations:
        grouped[(item.source_id, item.series_id)].append(item)
    resolved: list[CanonicalObservation] = []
    results: list[SeriesValidationResult] = []
    for series in sorted(series_plans, key=lambda item: (item.source_id, item.series_id)):
        rows, result = validate_series(
            grouped[(series.source_id, series.series_id)], series, reporting_period_end
        )
        resolved.extend(rows)
        results.append(result)
    return resolved, results
