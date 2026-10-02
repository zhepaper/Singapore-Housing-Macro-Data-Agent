from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Callable, Iterable

from housing_agent.models import Observation


def _observed(items: Iterable[Observation]) -> list[Observation]:
    return sorted((item for item in items if item.value is not None), key=lambda item: item.period)


def lagged_metric(
    items: Iterable[Observation],
    *,
    lag: int,
    suffix: str,
    unit: str,
    formula: Callable[[float, float], float],
    derivation: str,
) -> list[Observation]:
    rows = _observed(items)
    output: list[Observation] = []
    for index in range(lag, len(rows)):
        current, previous = rows[index], rows[index - lag]
        value = formula(float(current.value), float(previous.value))
        output.append(replace(
            current,
            series_id=f"{current.series_id}__{suffix}",
            series_label=f"{current.series_label} ({suffix})",
            value=value,
            unit=unit,
            role="derived",
            observation_status="derived",
            derivation=derivation,
        ))
    return output


def percent_change(items: Iterable[Observation], lag: int, suffix: str) -> list[Observation]:
    def formula(current: float, previous: float) -> float:
        if previous == 0:
            raise ValueError("Cannot calculate percentage change from zero")
        return (current / previous - 1.0) * 100.0

    return lagged_metric(
        items,
        lag=lag,
        suffix=suffix,
        unit="percent",
        formula=formula,
        derivation=f"(value / value_lag_{lag} - 1) * 100",
    )


def absolute_change(items: Iterable[Observation], lag: int, suffix: str, unit: str) -> list[Observation]:
    return lagged_metric(
        items,
        lag=lag,
        suffix=suffix,
        unit=unit,
        formula=lambda current, previous: current - previous,
        derivation=f"value - value_lag_{lag}",
    )


def derive_vacancy_rate(items: Iterable[Observation]) -> list[Observation]:
    available = {item.period: item for item in items if item.series_label == "Available Non-Landed Properties"}
    vacant = {item.period: item for item in items if item.series_label == "Vacant Non-Landed Properties"}
    periods = sorted(set(available) & set(vacant))
    output: list[Observation] = []
    for period in periods:
        denominator = available[period]
        numerator = vacant[period]
        if denominator.value == 0:
            raise ValueError(f"Zero available-unit denominator in {period}")
        if denominator.value is None or numerator.value is None:
            continue
        output.append(replace(
            numerator,
            series_id="private_non_landed_vacancy_rate__rate",
            series_label="Private non-landed vacancy rate",
            value=float(numerator.value) / float(denominator.value) * 100.0,
            unit="percent",
            role="derived",
            observation_status="derived",
            derivation="vacant_non_landed / available_non_landed * 100",
        ))
    return output


def derive_pipeline_under_construction_share(items: Iterable[Observation]) -> list[Observation]:
    total_label = "Total Non-Landed Properties"
    construction_label = "Total Non-Landed Properties / Under Construction"
    total = {item.period: item for item in items if item.series_label == total_label}
    construction = {item.period: item for item in items if item.series_label == construction_label}
    output: list[Observation] = []
    for period in sorted(set(total) & set(construction)):
        denominator = total[period]
        numerator = construction[period]
        if denominator.value == 0:
            raise ValueError(f"Zero total-pipeline denominator in {period}")
        if denominator.value is None or numerator.value is None:
            continue
        output.append(replace(
            numerator,
            series_id="private_residential_pipeline_supply__under_construction_share",
            series_label="Non-landed pipeline under-construction share",
            value=float(numerator.value) / float(denominator.value) * 100.0,
            unit="percent",
            role="derived",
            observation_status="derived",
            derivation="under_construction_non_landed / total_pipeline_non_landed * 100",
        ))
    return output


def month_to_quarter(period: str) -> tuple[str, int]:
    year, month_text = period.split("-")
    month = int(month_text)
    quarter = (month - 1) // 3 + 1
    return f"{year}-Q{quarter}", month


def quarterly_last_month_end(items: Iterable[Observation]) -> list[Observation]:
    groups: dict[str, list[tuple[int, Observation]]] = defaultdict(list)
    for item in _observed(items):
        quarter, month = month_to_quarter(item.period)
        groups[quarter].append((month, item))

    output: list[Observation] = []
    for quarter in sorted(groups):
        month, selected = max(groups[quarter], key=lambda pair: pair[0])
        quarter_number = int(quarter[-1])
        expected_month = quarter_number * 3
        incomplete = month != expected_month
        output.append(replace(
            selected,
            series_id=f"{selected.series_id}__quarter_end",
            series_label=f"{selected.series_label} (quarter representation)",
            period=quarter,
            frequency="quarterly",
            role="derived",
            observation_status="incomplete_period" if incomplete else "derived",
            source_observation_period=selected.period,
            quarter_incomplete=incomplete,
            derivation="last available month-end observation in quarter",
        ))
    return output
