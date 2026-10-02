import unittest

from housing_agent.models import Observation
from housing_agent.transforms import (
    absolute_change,
    derive_vacancy_rate,
    percent_change,
    quarterly_last_month_end,
)


def observation(label, period, value, frequency="quarterly"):
    return Observation(
        source_id="test", series_id=label.lower().replace(" ", "_"), series_label=label,
        period=period, frequency=frequency, value=value, unit="test", market="rent",
        role="predictor", observation_status="observed"
    )


class TransformTests(unittest.TestCase):
    def test_percent_change(self):
        result = percent_change([
            observation("Index", "2025-Q4", 100),
            observation("Index", "2026-Q1", 102),
        ], lag=1, suffix="qoq_pct")
        self.assertAlmostEqual(result[0].value, 2.0)

    def test_qoq_change_is_not_calculated_across_missing_quarter(self):
        result = percent_change([
            observation("Index", "2026-Q1", 100),
            observation("Index", "2026-Q3", 110),
        ], lag=1, suffix="qoq_pct")
        self.assertEqual(result, [])

    def test_yoy_change_requires_same_quarter_in_prior_year(self):
        result = percent_change([
            observation("Index", "2025-Q1", 100),
            observation("Index", "2026-Q2", 110),
        ], lag=4, suffix="yoy_pct")
        self.assertEqual(result, [])

    def test_annual_change_is_not_calculated_across_missing_year(self):
        result = percent_change([
            observation("Population", "2023", 100, "annual"),
            observation("Population", "2025", 110, "annual"),
        ], lag=1, suffix="yoy_pct")
        self.assertEqual(result, [])

    def test_lagged_metrics_do_not_cross_series(self):
        result = absolute_change([
            observation("Series A", "2026-Q1", 100),
            observation("Series B", "2026-Q2", 110),
        ], lag=1, suffix="qoq_change", unit="test")
        self.assertEqual(result, [])

    def test_vacancy_rate(self):
        result = derive_vacancy_rate([
            observation("Available Non-Landed Properties", "2026-Q2", 1000),
            observation("Vacant Non-Landed Properties", "2026-Q2", 50),
        ])
        self.assertEqual(result[0].value, 5.0)

    def test_partial_sora_quarter_is_marked(self):
        result = quarterly_last_month_end([
            observation("SORA", "2026-06", 1.78, "monthly"),
            observation("SORA", "2026-07", 2.01, "monthly"),
        ])
        self.assertFalse(result[0].quarter_incomplete)
        self.assertEqual(result[0].source_observation_period, "2026-06")
        self.assertTrue(result[1].quarter_incomplete)
        self.assertEqual(result[1].source_observation_period, "2026-07")


if __name__ == "__main__":
    unittest.main()
