from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable

from housing_agent.onboarding.discovery_models import AggregationMethod, ChangeMethod, SeriesType
from housing_agent.processing.models import (
    CanonicalObservation,
    FrozenSeriesPlan,
    TransformationTrace,
)


class TransformationFailure(ValueError):
    """An approved transformation cannot be applied without changing its policy."""


def period_ordinal(period: str, frequency: str) -> int:
    if frequency == "annual":
        return int(period)
    if frequency == "quarterly":
        year, quarter = period.split("-Q")
        return int(year) * 4 + int(quarter) - 1
    year, month = period.split("-")
    return int(year) * 12 + int(month) - 1


def shift_period(period: str, frequency: str, amount: int) -> str:
    ordinal = period_ordinal(period, frequency) + amount
    if frequency == "annual":
        return str(ordinal)
    divisor = 4 if frequency == "quarterly" else 12
    year, remainder = divmod(ordinal, divisor)
    return f"{year}-Q{remainder + 1}" if frequency == "quarterly" else f"{year}-{remainder + 1:02d}"


def _derived(
    base: CanonicalObservation,
    *,
    series_id: str,
    label_suffix: str,
    period: str,
    value: Decimal | None,
    unit: str,
    frequency: str,
    eligibility: str,
    derivation: str,
    source_periods: tuple[str, ...],
    input_series_ids: tuple[str, ...],
    raw_reference: str,
) -> CanonicalObservation:
    return base.model_copy(update={
        "series_id": series_id,
        "series_label": f"{base.series_label} ({label_suffix})",
        "period": period,
        "value": value,
        "unit": unit,
        "observation_frequency": frequency,
        "eligibility_status": eligibility,
        "raw_record_reference": raw_reference,
        "derivation": derivation,
        "source_periods": source_periods,
        "input_series_ids": input_series_ids,
    })


def aggregate_monthly_to_quarterly(
    observations: Iterable[CanonicalObservation],
    series: FrozenSeriesPlan,
) -> tuple[list[CanonicalObservation], list[TransformationTrace]]:
    view = series.preparation_contract.quarterly_comparison
    if view is None:
        return [], []
    if series.observation_frequency != "monthly":
        raise TransformationFailure("quarterly comparison is only valid for monthly inputs")
    method = view.aggregation_method
    if method == AggregationMethod.SUM and series.series_type != SeriesType.FLOW:
        raise TransformationFailure("quarterly sum is allowed only for flow series")
    if method == AggregationMethod.PRESERVE or method == AggregationMethod.NOT_APPLICABLE:
        raise TransformationFailure("monthly quarterly view requires mean, last, or sum")
    groups: dict[str, list[CanonicalObservation]] = defaultdict(list)
    for item in observations:
        if item.eligibility_status not in {"eligible", "missing_at_source"}:
            continue
        year, month = item.period.split("-")
        quarter = (int(month) - 1) // 3 + 1
        groups[f"{year}-Q{quarter}"].append(item)
    output: list[CanonicalObservation] = []
    traces: list[TransformationTrace] = []
    for quarter, rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda item: item.period)
        expected = {
            f"{quarter[:4]}-{month:02d}"
            for month in range((int(quarter[-1]) - 1) * 3 + 1, int(quarter[-1]) * 3 + 1)
        }
        complete = {item.period for item in rows if item.value is not None} == expected
        if not complete and view.incomplete_period_policy == "reject":
            traces.append(TransformationTrace(
                operation_id=f"{series.series_id}:exclude_incomplete:{quarter}",
                operation="incomplete_period_excluded",
                source_id=series.source_id,
                output_series_id=f"{series.series_id}__quarterly_{method.value}",
                parameters={"method": method.value, "incomplete_policy": "reject"},
                input_periods=tuple(item.period for item in rows),
                output_period=quarter,
            ))
            continue
        available = [item for item in rows if item.value is not None]
        value: Decimal | None = None
        if available:
            if method == AggregationMethod.LAST:
                value = available[-1].value
            elif method == AggregationMethod.MEAN:
                value = sum((item.value for item in available if item.value is not None), Decimal("0")) / Decimal(len(available))
            elif method == AggregationMethod.SUM:
                value = sum((item.value for item in available if item.value is not None), Decimal("0"))
        base = rows[-1]
        source_periods = tuple(item.period for item in rows)
        output_id = f"{series.series_id}__quarterly_{method.value}"
        output.append(_derived(
            base,
            series_id=output_id,
            label_suffix=f"quarterly {method.value}",
            period=quarter,
            value=value,
            unit=series.unit,
            frequency="quarterly",
            eligibility="eligible" if complete else "incomplete_period",
            derivation=f"monthly to quarterly {method.value}; policy={view.incomplete_period_policy}",
            source_periods=source_periods,
            input_series_ids=tuple(series.series_id for _ in rows),
            raw_reference="|".join(item.raw_record_reference for item in rows),
        ))
        traces.append(TransformationTrace(
            operation_id=f"{series.series_id}:aggregate:{quarter}",
            operation="monthly_to_quarterly",
            source_id=series.source_id,
            output_series_id=output_id,
            parameters={"method": method.value, "incomplete_policy": view.incomplete_period_policy},
            input_periods=source_periods,
            output_period=quarter,
        ))
    return output, traces


def _allowed_change(series_type: SeriesType, method: ChangeMethod) -> bool:
    if method == ChangeMethod.PUBLISHED_CHANGE:
        return True
    if series_type == SeriesType.RATE:
        return method in {
            ChangeMethod.ABSOLUTE,
            ChangeMethod.PERCENTAGE_POINT,
            ChangeMethod.BASIS_POINT,
        }
    return method in {ChangeMethod.ABSOLUTE, ChangeMethod.PERCENT}


def calculate_changes(
    observations: Iterable[CanonicalObservation],
    series: FrozenSeriesPlan,
    comparison: Iterable[CanonicalObservation],
) -> tuple[list[CanonicalObservation], list[TransformationTrace]]:
    native = list(observations)
    comparison_rows = list(comparison)
    output: list[CanonicalObservation] = []
    traces: list[TransformationTrace] = []
    for calculation in series.preparation_contract.change_calculations:
        if calculation.method == ChangeMethod.PUBLISHED_CHANGE:
            continue
        if not _allowed_change(series.series_type, calculation.method):
            raise TransformationFailure(
                f"{calculation.method.value} is not valid for {series.series_type.value} series"
            )
        inputs = native if calculation.input_view == "native" else comparison_rows
        eligible = [
            item for item in inputs
            if item.eligibility_status == "eligible" and item.value is not None
        ]
        by_ordinal = {
            period_ordinal(item.period, item.observation_frequency): item for item in eligible
        }
        if len(by_ordinal) != len(eligible):
            raise TransformationFailure("changes require unique calendar periods")
        suffix = f"{calculation.horizon}_{calculation.method.value}"
        for current_ordinal, current in sorted(by_ordinal.items()):
            previous = by_ordinal.get(current_ordinal - calculation.lag_periods)
            if previous is None:
                continue
            assert current.value is not None and previous.value is not None
            if calculation.method == ChangeMethod.PERCENT:
                if previous.value == 0:
                    raise TransformationFailure("percentage change cannot use a zero denominator")
                value = (current.value / previous.value - Decimal("1")) * Decimal("100")
                unit = "percent"
            elif calculation.method == ChangeMethod.BASIS_POINT:
                value = (current.value - previous.value) * Decimal("100")
                unit = "basis points"
            else:
                value = current.value - previous.value
                unit = "percentage points" if calculation.method == ChangeMethod.PERCENTAGE_POINT else current.unit
            output_id = f"{current.series_id}__{suffix}"
            output.append(_derived(
                current,
                series_id=output_id,
                label_suffix=suffix,
                period=current.period,
                value=value,
                unit=unit,
                frequency=current.observation_frequency,
                eligibility="eligible",
                derivation=f"{calculation.method.value} using calendar lag {calculation.lag_periods}",
                source_periods=(previous.period, current.period),
                input_series_ids=(previous.series_id, current.series_id),
                raw_reference=f"{previous.raw_record_reference}|{current.raw_record_reference}",
            ))
            traces.append(TransformationTrace(
                operation_id=f"{series.series_id}:change:{suffix}:{current.period}",
                operation="calendar_change",
                source_id=series.source_id,
                output_series_id=output_id,
                parameters={
                    "horizon": calculation.horizon,
                    "method": calculation.method.value,
                    "lag_periods": calculation.lag_periods,
                },
                input_periods=(previous.period, current.period),
                output_period=current.period,
            ))
    return output, traces


def apply_predictive_lag(
    observations: Iterable[CanonicalObservation],
    series: FrozenSeriesPlan,
    comparison: Iterable[CanonicalObservation],
) -> tuple[list[CanonicalObservation], list[TransformationTrace]]:
    alignment = series.preparation_contract.predictive_alignment
    if alignment is None:
        return [], []
    inputs = list(comparison) if series.observation_frequency == "monthly" else list(observations)
    output: list[CanonicalObservation] = []
    traces: list[TransformationTrace] = []
    for item in inputs:
        if item.observation_frequency != "quarterly" or item.eligibility_status != "eligible":
            continue
        target = shift_period(item.period, "quarterly", alignment.lag_periods)
        output_id = f"{item.series_id}__predictive_lag_{alignment.lag_periods}"
        output.append(_derived(
            item,
            series_id=output_id,
            label_suffix=f"predictive lag {alignment.lag_periods}",
            period=target,
            value=item.value,
            unit=item.unit,
            frequency="quarterly",
            eligibility="eligible",
            derivation=f"source value aligned to outcome {alignment.lag_periods} quarter(s) later",
            source_periods=(item.period,),
            input_series_ids=(item.series_id,),
            raw_reference=item.raw_record_reference,
        ))
        traces.append(TransformationTrace(
            operation_id=f"{series.series_id}:lag:{item.period}:{target}",
            operation="calendar_lag",
            source_id=series.source_id,
            output_series_id=output_id,
            parameters={"lag_quarters": alignment.lag_periods},
            input_periods=(item.period,),
            output_period=target,
        ))
    return output, traces


def transform_series(
    observations: Iterable[CanonicalObservation],
    series: FrozenSeriesPlan,
) -> tuple[list[CanonicalObservation], list[TransformationTrace]]:
    native = list(observations)
    comparison, aggregation_trace = aggregate_monthly_to_quarterly(native, series)
    changes, change_trace = calculate_changes(native, series, comparison)
    lagged, lag_trace = apply_predictive_lag(native, series, comparison)
    return [*comparison, *changes, *lagged], [*aggregation_trace, *change_trace, *lag_trace]
