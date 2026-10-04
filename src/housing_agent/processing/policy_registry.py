from __future__ import annotations

from enum import Enum

from housing_agent.onboarding.discovery_models import (
    AggregationMethod,
    ChangeMethod,
    SeriesType,
)


class DerivedOperation(str, Enum):
    RATIO = "ratio"
    SHARE_OF_TOTAL = "share_of_total"
    SUM = "sum"
    DIFFERENCE = "difference"


ALLOWED_DERIVED_OPERATIONS = frozenset(DerivedOperation)

ALLOWED_CHANGE_METHODS = {
    SeriesType.RATE: frozenset({
        ChangeMethod.ABSOLUTE,
        ChangeMethod.PERCENTAGE_POINT,
        ChangeMethod.BASIS_POINT,
        ChangeMethod.PUBLISHED_CHANGE,
    }),
    SeriesType.INDEX: frozenset({ChangeMethod.ABSOLUTE, ChangeMethod.PERCENT}),
    SeriesType.STOCK: frozenset({ChangeMethod.ABSOLUTE, ChangeMethod.PERCENT}),
    SeriesType.FLOW: frozenset({
        ChangeMethod.ABSOLUTE,
        ChangeMethod.PERCENT,
        ChangeMethod.PUBLISHED_CHANGE,
    }),
}

ALLOWED_QUARTERLY_AGGREGATIONS = {
    SeriesType.RATE: frozenset({AggregationMethod.LAST, AggregationMethod.MEAN}),
    SeriesType.INDEX: frozenset({AggregationMethod.LAST, AggregationMethod.MEAN}),
    SeriesType.STOCK: frozenset({AggregationMethod.LAST, AggregationMethod.MEAN}),
    SeriesType.FLOW: frozenset({
        AggregationMethod.LAST,
        AggregationMethod.MEAN,
        AggregationMethod.SUM,
    }),
}


def change_method_allowed(series_type: SeriesType, method: ChangeMethod) -> bool:
    return method in ALLOWED_CHANGE_METHODS[series_type]


def quarterly_aggregation_allowed(
    series_type: SeriesType, method: AggregationMethod
) -> bool:
    return method in ALLOWED_QUARTERLY_AGGREGATIONS[series_type]
