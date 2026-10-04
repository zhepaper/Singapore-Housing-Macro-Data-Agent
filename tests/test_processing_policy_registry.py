from __future__ import annotations

import unittest

from housing_agent.onboarding.discovery_models import (
    AggregationMethod,
    ChangeMethod,
    SeriesType,
)
from housing_agent.processing.policy_registry import (
    ALLOWED_DERIVED_OPERATIONS,
    DerivedOperation,
    change_method_allowed,
    quarterly_aggregation_allowed,
)


class ProcessingPolicyRegistryTests(unittest.TestCase):
    def test_derived_operation_registry_is_explicit_and_bounded(self) -> None:
        self.assertEqual(
            {item.value for item in ALLOWED_DERIVED_OPERATIONS},
            {"ratio", "share_of_total", "sum", "difference"},
        )

    def test_rate_and_flow_aggregation_policies_are_distinct(self) -> None:
        self.assertFalse(
            quarterly_aggregation_allowed(SeriesType.RATE, AggregationMethod.SUM)
        )
        self.assertTrue(
            quarterly_aggregation_allowed(SeriesType.FLOW, AggregationMethod.SUM)
        )

    def test_change_units_are_restricted_by_series_type(self) -> None:
        self.assertTrue(
            change_method_allowed(SeriesType.RATE, ChangeMethod.BASIS_POINT)
        )
        self.assertFalse(
            change_method_allowed(SeriesType.INDEX, ChangeMethod.BASIS_POINT)
        )
        self.assertIn(DerivedOperation.RATIO, ALLOWED_DERIVED_OPERATIONS)


if __name__ == "__main__":
    unittest.main()
