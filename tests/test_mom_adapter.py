import unittest

from housing_agent.adapters.mom import parse_mom_non_resident_employment, previous_quarter


class MomAdapterTests(unittest.TestCase):
    def test_previous_quarter_year_boundary(self):
        self.assertEqual(previous_quarter(2026, 1), "2025-Q4")

    def test_parse_final_report_excerpt(self):
        body = b"""
        <p>Released on: 21 September 2026</p>
        <p>Total employment expanded by 11,400 in 2Q 2026. The stronger quarterly
        increase was driven by non-resident employment, which grew by 9,200, up
        from 4,100 in the previous quarter.</p>
        """
        source = {"source_id": "non_resident_employment_change", "unit": "persons"}
        result = parse_mom_non_resident_employment(body, source)
        self.assertEqual([(item.period, item.value) for item in result], [
            ("2026-Q1", 4100.0), ("2026-Q2", 9200.0)
        ])
        self.assertEqual(result[1].release_date, "2026-09-21")


if __name__ == "__main__":
    unittest.main()
