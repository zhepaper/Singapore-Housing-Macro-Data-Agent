from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from housing_agent.models import Observation
from housing_agent.onboarding.discovery_models import AggregationMethod, ChangeMethod
from housing_agent.preparation.models import ExecutionTrace, PreparationContract
from housing_agent.transforms import absolute_change, lagged_metric, percent_change


def _month_parts(period: str) -> tuple[int, int]:
    try:
        year_text, month_text = period.split("-")
        year, month = int(year_text), int(month_text)
    except Exception as exc:
        raise ValueError(f"Invalid monthly period: {period!r}") from exc
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid monthly period: {period!r}")
    return year, month


def _quarter_for_month(period: str) -> tuple[str, int]:
    year, month = _month_parts(period)
    quarter = (month - 1) // 3 + 1
    return f"{year}-Q{quarter}", month


def _quarterly_view(
    observations: list[Observation], contract: PreparationContract
) -> list[Observation]:
    view = contract.quarterly_comparison
    if view is None:
        return []
    groups: dict[tuple[str, str], list[tuple[int, Observation]]] = defaultdict(list)
    for item in observations:
        quarter, month = _quarter_for_month(item.period)
        groups[(item.series_id, quarter)].append((month, item))
    output: list[Observation] = []
    for (_, quarter), rows in sorted(groups.items()):
        quarter_number = int(quarter[-1])
        expected_months = set(range(quarter_number * 3 - 2, quarter_number * 3 + 1))
        present_months = {month for month, item in rows if item.value is not None}
        incomplete = present_months != expected_months
        if incomplete and view.incomplete_period_policy == "reject":
            raise ValueError(f"Incomplete quarter {quarter} under reject policy")
        observed = [(month, item) for month, item in rows if item.value is not None]
        base = max(rows, key=lambda pair: pair[0])[1]
        value: float | None
        source_periods: tuple[str, ...]
        if not observed:
            value = None
            source_periods = tuple(item.period for _, item in sorted(rows))
        elif view.aggregation_method == AggregationMethod.LAST:
            _, selected = max(observed, key=lambda pair: pair[0])
            value = float(selected.value)
            source_periods = (selected.period,)
            base = selected
        else:
            values = [float(item.value) for _, item in observed]
            value = (
                sum(values) / len(values)
                if view.aggregation_method == AggregationMethod.MEAN
                else sum(values)
            )
            source_periods = tuple(item.period for _, item in sorted(observed))
        output.append(replace(
            base,
            series_id=f"{base.series_id}__quarterly_{view.aggregation_method.value}",
            series_label=(
                f"{base.series_label} (quarterly {view.aggregation_method.value})"
            ),
            period=quarter,
            frequency="quarterly",
            value=value,
            role="derived",
            observation_status=(
                "incomplete_period" if incomplete else "derived"
            ),
            source_observation_period=None,
            quarter_incomplete=incomplete,
            derivation=(
                f"monthly to quarterly using {view.aggregation_method.value}; "
                f"missing values preserved, policy={view.incomplete_period_policy}"
            ),
            source_periods=source_periods,
            input_series_ids=tuple(item.series_id for _, item in sorted(rows)),
        ))
    return output


def _calculate_changes(
    native: list[Observation],
    comparison: list[Observation],
    contract: PreparationContract,
) -> list[Observation]:
    output: list[Observation] = []
    for calculation in contract.change_calculations:
        items = native if calculation.input_view == "native" else comparison
        suffix = f"{calculation.horizon}_{calculation.method.value}"
        if calculation.method == ChangeMethod.PUBLISHED_CHANGE:
            continue
        if calculation.method == ChangeMethod.PERCENT:
            output.extend(percent_change(items, calculation.lag_periods, suffix))
        elif calculation.method == ChangeMethod.BASIS_POINT:
            output.extend(lagged_metric(
                items,
                lag=calculation.lag_periods,
                suffix=suffix,
                unit="basis points",
                formula=lambda current, previous: (current - previous) * 100.0,
                derivation=(
                    f"(value - value_lag_{calculation.lag_periods}) * 100"
                ),
            ))
        else:
            unit = (
                "percentage points"
                if calculation.method == ChangeMethod.PERCENTAGE_POINT
                else items[0].unit if items else "source unit"
            )
            output.extend(absolute_change(
                items,
                calculation.lag_periods,
                suffix,
                unit,
            ))
    return output


def _shift_quarter(period: str, lag: int) -> str:
    year_text, quarter_text = period.split("-Q")
    ordinal = int(year_text) * 4 + int(quarter_text) - 1 + lag
    return f"{ordinal // 4}-Q{ordinal % 4 + 1}"


def _predictive_view(
    native: list[Observation],
    comparison: list[Observation],
    contract: PreparationContract,
) -> list[Observation]:
    alignment = contract.predictive_alignment
    if alignment is None:
        return []
    inputs = comparison if contract.native_frequency == "monthly" else native
    output: list[Observation] = []
    for item in inputs:
        if item.frequency != "quarterly":
            raise ValueError("Predictive alignment requires quarterly observations")
        target_period = _shift_quarter(item.period, alignment.lag_periods)
        output.append(replace(
            item,
            series_id=f"{item.series_id}__predictive_lag_{alignment.lag_periods}",
            series_label=(
                f"{item.series_label} (aligned {alignment.lag_periods} quarter(s) ahead)"
            ),
            period=target_period,
            role="derived",
            observation_status="derived" if item.value is not None else item.observation_status,
            derivation=(
                "exploratory predictive alignment: source value assigned to outcome "
                f"period {alignment.lag_periods} quarter(s) later"
            ),
            source_periods=(item.period,),
            input_series_ids=(item.series_id,),
        ))
    return output


def execute_preparation_contract(
    observations: Iterable[Observation],
    contract: PreparationContract,
) -> tuple[list[Observation], ExecutionTrace]:
    native = sorted(list(observations), key=lambda item: item.period)
    if any(item.source_id != contract.source_id for item in native):
        raise ValueError("All observations must match the approved contract source_id")
    if any(item.frequency != contract.native_frequency for item in native):
        raise ValueError("Observation frequency does not match the approved contract")
    comparison = _quarterly_view(native, contract)
    changes = _calculate_changes(native, comparison, contract)
    predictive = _predictive_view(native, comparison, contract)
    output = [*native, *comparison, *changes, *predictive]
    operations = ["preserve_native"]
    if contract.quarterly_comparison:
        operations.append(
            f"quarterly_{contract.quarterly_comparison.aggregation_method.value}"
        )
    operations.extend(
        f"{item.input_view}:{item.horizon}:{item.method.value}"
        for item in contract.change_calculations
    )
    if contract.predictive_alignment:
        operations.append(
            f"predictive_lag_{contract.predictive_alignment.lag_periods}_quarters"
        )
    return output, ExecutionTrace(
        source_id=contract.source_id,
        input_observations=len(native),
        native_observations=len(native),
        comparison_observations=len(comparison),
        change_observations=len(changes),
        output_observations=len(output),
        operations=operations,
    )
