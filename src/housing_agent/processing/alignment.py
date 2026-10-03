from __future__ import annotations

import math
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from itertools import combinations
from typing import Iterable

from housing_agent.processing.models import (
    AlignedDataset,
    CanonicalObservation,
    CrossSeriesValidationResult,
    FrozenDataPlan,
    ProcessingIssue,
    RecoveryRoute,
)


def _quarter_end(period: str) -> date:
    year_text, quarter_text = period.split("-Q")
    year, month = int(year_text), int(quarter_text) * 3
    return date(year, month, monthrange(year, month)[1])


def align_market_dataset(
    observations: Iterable[CanonicalObservation], market: str
) -> AlignedDataset:
    candidates = [
        item for item in observations
        if item.observation_frequency == "quarterly"
        and item.eligibility_status == "eligible"
        and item.value is not None
        and item.portfolio_role != "structural_context"
        and item.market_role in {market, "shared"}
    ]
    lagged_sources = {
        item.source_id for item in candidates
        if item.portfolio_role == "predictor" and "__predictive_lag_" in item.series_id
    }
    selected = [
        item for item in candidates
        if item.portfolio_role != "predictor"
        or item.source_id not in lagged_sources
        or "__predictive_lag_" in item.series_id
    ]
    by_series: dict[str, dict[str, CanonicalObservation]] = defaultdict(dict)
    for item in selected:
        if item.period in by_series[item.series_id]:
            raise ValueError(
                f"duplicate aligned value for {item.series_id} in {item.period}"
            )
        by_series[item.series_id][item.period] = item
    series_ids = tuple(sorted(by_series))
    common = set.intersection(
        *(set(by_series[series_id]) for series_id in series_ids)
    ) if series_ids else set()
    rows = tuple(
        {
            "period": period,
            **{
                series_id: str(by_series[series_id][period].value)
                for series_id in series_ids
            },
        }
        for period in sorted(common)
    )
    return AlignedDataset(
        market=market,
        periods=tuple(sorted(common)),
        series_ids=series_ids,
        rows=rows,
    )


def _correlation(rows: tuple[dict[str, object], ...], left: str, right: str) -> float | None:
    pairs = [
        (float(row[left]), float(row[right]))
        for row in rows if left in row and right in row
    ]
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else None


def validate_cross_series(
    plan: FrozenDataPlan,
    observations: Iterable[CanonicalObservation],
    sale: AlignedDataset,
    rent: AlignedDataset,
) -> CrossSeriesValidationResult:
    rows = list(observations)
    issues: list[ProcessingIssue] = []
    for dataset in (sale, rent):
        outcome_ids = {
            item.series_id for item in rows
            if item.portfolio_role == "outcome"
            and item.market_role == dataset.market
            and item.observation_frequency == "quarterly"
        }
        if not outcome_ids.intersection(dataset.series_ids):
            issues.append(ProcessingIssue(
                code="OUTCOME_ALIGNMENT_MISSING",
                severity="error",
                route=RecoveryRoute.HUMAN_REVIEW,
                message=f"The {dataset.market} aligned dataset has no quarterly outcome.",
            ))
        if len(dataset.periods) < plan.minimum_quarterly_observations:
            issues.append(ProcessingIssue(
                code="INSUFFICIENT_COMMON_WINDOW",
                severity="error",
                route=RecoveryRoute.HUMAN_REVIEW,
                message=(
                    f"The {dataset.market} dataset has {len(dataset.periods)} common quarters; "
                    f"the approved minimum is {plan.minimum_quarterly_observations}."
                ),
            ))

        predictor_ids = {
            item.series_id for item in rows
            if item.portfolio_role == "predictor" and item.series_id in dataset.series_ids
        }
        for left, right in combinations(sorted(predictor_ids), 2):
            correlation = _correlation(dataset.rows, left, right)
            if correlation is not None and abs(correlation) >= float(plan.feature_redundancy_threshold):
                issues.append(ProcessingIssue(
                    code="HIGH_FEATURE_REDUNDANCY",
                    severity="warning",
                    route=RecoveryRoute.HUMAN_REVIEW,
                    message=(
                        f"{left} and {right} have absolute correlation {abs(correlation):.3f}, "
                        "above the approved review threshold."
                    ),
                ))

    aligned_ids = set(sale.series_ids) | set(rent.series_ids)
    for item in rows:
        if (
            item.portfolio_role == "predictor"
            and item.series_id in aligned_ids
            and item.observation_frequency == "quarterly"
            and item.eligibility_status == "eligible"
            and item.available_date is not None
            and item.available_date > _quarter_end(item.period)
        ):
            issues.append(ProcessingIssue(
                code="POTENTIAL_LOOK_AHEAD",
                severity="error",
                route=RecoveryRoute.HUMAN_REVIEW,
                message="Predictor was not available by the end of its aligned outcome quarter.",
                source_id=item.source_id,
                series_id=item.series_id,
                period=item.period,
            ))
    all_periods = sorted(set(sale.periods) | set(rent.periods))
    status = (
        "fail" if any(item.severity == "error" for item in issues)
        else "warning" if issues else "pass"
    )
    return CrossSeriesValidationResult(
        status=status,
        common_period_start=all_periods[0] if all_periods else None,
        common_period_end=all_periods[-1] if all_periods else None,
        sale_observation_count=len(sale.periods),
        rent_observation_count=len(rent.periods),
        issues=tuple(issues),
    )
