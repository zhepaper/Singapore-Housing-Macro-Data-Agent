import unittest
import json
from pathlib import Path

from housing_agent.adapters.datagov import canonical_period, normalize_datagov, parse_number


class DataGovAdapterTests(unittest.TestCase):
    def test_golden_price_fixture(self):
        payload = json.loads(
            (Path(__file__).parent / "fixtures/datagov_non_landed_price.json").read_text()
        )
        source = {
            "source_id": "price", "role": "benchmark", "market": "sale",
            "unit": "index", "period_field": "quarter", "value_field": "index",
            "selector": {"property_type": "Non-Landed"},
        }
        result = normalize_datagov(payload, source)
        self.assertEqual([(row.period, row.value) for row in result], [
            ("2026-Q1", 201.2), ("2026-Q2", 202.4)
        ])

    def test_period_formats(self):
        self.assertEqual(canonical_period("2026-Q2"), ("2026-Q2", "quarterly"))
        self.assertEqual(canonical_period("20262Q"), ("2026-Q2", "quarterly"))
        self.assertEqual(canonical_period("2026Jul"), ("2026-07", "monthly"))
        self.assertEqual(canonical_period("2025"), ("2025", "annual"))

    def test_missing_is_not_zero(self):
        self.assertIsNone(parse_number("na"))
        self.assertEqual(parse_number("0"), 0.0)

    def test_long_form_selector(self):
        source = {
            "source_id": "price",
            "role": "benchmark",
            "market": "sale",
            "unit": "index",
            "period_field": "quarter",
            "value_field": "index",
            "selector": {"property_type": "Non-Landed"},
        }
        payload = {"success": True, "result": {"records": [
            {"quarter": "2026-Q1", "property_type": "All Residential", "index": "100"},
            {"quarter": "2026-Q1", "property_type": "Non-Landed", "index": "101.2"},
        ]}}
        result = normalize_datagov(payload, source)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].value, 101.2)

    def test_grouped_wide_rows_are_qualified(self):
        source = {
            "source_id": "pipeline",
            "role": "predictor",
            "market": "shared",
            "unit": "dwelling units",
            "series_field": "DataSeries",
            "series_group": "Total Non-Landed Properties",
        }
        payload = {"success": True, "result": {"records": [
            {"_id": 1, "DataSeries": "Total Landed Properties", "20262Q": "10"},
            {"_id": 2, "DataSeries": "  Under Construction", "20262Q": "8"},
            {"_id": 3, "DataSeries": "Total Non-Landed Properties", "20262Q": "100"},
            {"_id": 4, "DataSeries": "  Under Construction", "20262Q": "80"},
        ]}}
        result = normalize_datagov(payload, source)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            {item.series_label for item in result},
            {"Total Non-Landed Properties", "Total Non-Landed Properties / Under Construction"},
        )

    def test_missing_or_renamed_series_fails_closed(self):
        source = {
            "source_id": "rate", "role": "predictor", "market": "sale",
            "unit": "percent", "series_field": "DataSeries",
            "selected_series_labels": ["Exact Official Series"],
        }
        payload = {"success": True, "result": {"records": [
            {"DataSeries": "Renamed Official Series", "2026Jul": "1.5"}
        ]}}
        with self.assertRaisesRegex(ValueError, "Configured series selection"):
            normalize_datagov(payload, source)

    def test_duplicate_periods_fail_closed(self):
        source = {
            "source_id": "price", "role": "benchmark", "market": "sale",
            "unit": "index", "period_field": "quarter", "value_field": "index",
            "selector": {"property_type": "Non-Landed"},
        }
        payload = {"success": True, "result": {"records": [
            {"quarter": "2026-Q1", "property_type": "Non-Landed", "index": "100"},
            {"quarter": "2026-Q1", "property_type": "Non-Landed", "index": "101"},
        ]}}
        with self.assertRaisesRegex(ValueError, "Duplicate normalized"):
            normalize_datagov(payload, source)


if __name__ == "__main__":
    unittest.main()
