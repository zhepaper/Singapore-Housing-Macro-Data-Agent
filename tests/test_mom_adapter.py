import unittest
from pathlib import Path

from housing_agent.adapters.mom import parse_mom_non_resident_employment, previous_quarter


class MomAdapterTests(unittest.TestCase):
    def test_previous_quarter_year_boundary(self):
        self.assertEqual(previous_quarter(2026, 1), "2025-Q4")

    def test_parse_final_report_excerpt(self):
        body = (Path(__file__).parent / "fixtures/mom_non_resident_employment.html").read_bytes()
        source = {"source_id": "non_resident_employment_change", "unit": "persons"}
        result = parse_mom_non_resident_employment(body, source)
        self.assertEqual([(item.period, item.value) for item in result], [
            ("2026-Q1", 4100.0), ("2026-Q2", 9200.0)
        ])
        self.assertEqual(result[1].release_date, "2026-09-21")

    def test_changed_report_wording_fails_closed(self):
        body = b"""
        <p>Released on: 21 September 2026</p>
        <p>Total employment rose during 2Q 2026. Foreign workforce additions
        accounted for most of the increase.</p>
        """
        source = {"source_id": "non_resident_employment_change", "unit": "persons"}
        with self.assertRaisesRegex(ValueError, "Could not identify|unambiguously parse"):
            parse_mom_non_resident_employment(body, source)


if __name__ == "__main__":
    unittest.main()
