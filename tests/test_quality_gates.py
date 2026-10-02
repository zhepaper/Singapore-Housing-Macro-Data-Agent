import unittest
from datetime import date

from housing_agent.models import Observation
from housing_agent.transforms import derive_vacancy_rate
from housing_agent.workflow import freshness_status, validate_node


class QualityGateTests(unittest.TestCase):
    def test_quarterly_series_is_current_before_next_release_due(self):
        result = freshness_status("2026-Q2", 35, date(2026, 10, 1))
        self.assertEqual(result["status"], "not_yet_released")

    def test_quarterly_series_becomes_stale_after_release_due(self):
        result = freshness_status("2026-Q2", 35, date(2026, 12, 15))
        self.assertEqual(result["status"], "stale")

    def test_history_truncation_fails_validation(self):
        state = {
            "reporting_as_of_date": "2026-10-01",
            "catalog": {"sources": [{
                "source_id": "short",
                "minimum_normalized_observations": 3,
                "freshness_rule": {"expected_lag_days": 35},
            }]},
            "observations": [{
                "source_id": "short", "series_id": "short__value", "period": "2026-Q2"
            }],
            "derived_observations": [],
            "validation_errors": [],
        }
        result = validate_node(state)
        self.assertTrue(any("expected at least" in error for error in result["validation_errors"]))

    def test_zero_vacancy_denominator_is_rejected(self):
        common = dict(
            source_id="vacancy", frequency="quarterly", unit="dwelling units",
            market="rent", role="predictor", observation_status="observed",
        )
        with self.assertRaisesRegex(ValueError, "Zero available-unit denominator"):
            derive_vacancy_rate([
                Observation(series_id="available", series_label="Available Non-Landed Properties",
                            period="2026-Q2", value=0, **common),
                Observation(series_id="vacant", series_label="Vacant Non-Landed Properties",
                            period="2026-Q2", value=10, **common),
            ])

    def test_unexpected_unit_and_invalid_period_fail_validation(self):
        state = {
            "reporting_as_of_date": "2026-10-01",
            "catalog": {"sources": [{
                "source_id": "series", "unit": "persons",
                "minimum_normalized_observations": 1,
                "freshness_rule": {"expected_lag_days": 35},
            }]},
            "observations": [{
                "source_id": "series", "series_id": "series__value",
                "period": "bad-period", "unit": "percent",
            }],
            "derived_observations": [],
            "validation_errors": [],
        }
        result = validate_node(state)
        self.assertTrue(any("Invalid or missing period" in error for error in result["validation_errors"]))
        self.assertTrue(any("unexpected unit" in error for error in result["validation_errors"]))
        self.assertTrue(result["requires_human_review"])

    def test_duplicate_period_fails_validation(self):
        item = {
            "source_id": "series", "series_id": "series__value",
            "period": "2026-Q2", "unit": "persons",
        }
        state = {
            "reporting_as_of_date": "2026-10-01",
            "catalog": {"sources": [{
                "source_id": "series", "unit": "persons",
                "minimum_normalized_observations": 1,
                "freshness_rule": {"expected_lag_days": 35},
            }]},
            "observations": [item, dict(item)], "derived_observations": [],
            "validation_errors": [],
        }
        result = validate_node(state)
        self.assertTrue(any("Duplicate observation" in error for error in result["validation_errors"]))


if __name__ == "__main__":
    unittest.main()
