from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from housing_agent.onboarding.discovery_models import SeriesType
from housing_agent.processing.models import FrozenDataPlan, FrozenSeriesPlan, MappingContract
from housing_agent.processing.normalization import MappingFailure, normalize_series
from housing_agent.processing.validation import validate_series
from tests.test_processing_integrity import _preparation


def _make_plan(path: Path, mapping: MappingContract, *, market: str = "sale") -> tuple[FrozenDataPlan, FrozenSeriesPlan]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    item = FrozenSeriesPlan(
        source_id=mapping.source_id,
        series_id=mapping.series_id,
        series_label="Test housing index",
        snapshot_path=str(path),
        snapshot_sha256=digest,
        mapping_contract=mapping,
        preparation_contract=_preparation(mapping.source_id, mapping.series_id, "monthly"),
        definition="Official monthly test housing index.",
        unit="index points",
        observation_frequency="monthly",
        update_frequency="monthly",
        series_type=SeriesType.INDEX,
        portfolio_role="outcome",
        market_role=market,
        release_lag_days=15,
    )
    draft = FrozenDataPlan(
        plan_id="normalization_test",
        plan_version=1,
        plan_sha256="0" * 64,
        approval_status="approved",
        approved_by="Test reviewer",
        approved_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        reporting_as_of_date=date(2026, 6, 30),
        historical_start_date=date(2026, 1, 1),
        historical_end_date=date(2026, 6, 30),
        series=(item,),
    )
    return draft.model_copy(update={"plan_sha256": draft.computed_sha256()}), item


class ProcessingNormalizationTests(unittest.TestCase):
    def test_xlsx_long_layout_uses_approved_sheet_and_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "series.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Data"
            sheet.append(["period", "value"])
            sheet.append(["2026-01", 12.5])
            sheet.append(["2026-02", 13.0])
            workbook.save(path)
            mapping = MappingContract(
                contract_version="1",
                source_id="test_source",
                series_id="test_index",
                source_format="xlsx",
                layout="long",
                sheet_name="Data",
                date_field="period",
                value_field="value",
            )
            plan, series = _make_plan(path, mapping)

            rows = normalize_series(plan, series)

            self.assertEqual([item.period for item in rows], ["2026-01", "2026-02"])
            self.assertEqual(rows[0].value, Decimal("12.5"))

    def test_long_csv_preserves_missing_and_marks_after_as_of(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "series.csv"
            path.write_text(
                "period,value\n2026-05,100.5\n2026-06,-\n2026-07,102\n",
                encoding="utf-8",
            )
            mapping = MappingContract(
                contract_version="1",
                source_id="test_source",
                series_id="test_index",
                source_format="csv",
                layout="long",
                date_field="period",
                value_field="value",
            )
            plan, series = _make_plan(path, mapping)

            rows = normalize_series(plan, series)

            self.assertEqual(rows[0].value, Decimal("100.5"))
            self.assertEqual(rows[1].eligibility_status, "missing_at_source")
            self.assertIsNone(rows[1].value)
            self.assertEqual(rows[2].eligibility_status, "after_as_of")
            self.assertEqual(rows[0].raw_record_reference, "record:0/field:value")

    def test_wide_json_records_path_and_scale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "series.json"
            path.write_text(
                '{"result":{"records":[{"series":"Target","2026Jan":"1.2","2026Feb":"1.3"}]}}',
                encoding="utf-8",
            )
            mapping = MappingContract(
                contract_version="1",
                source_id="test_source",
                series_id="test_index",
                source_format="json",
                layout="wide",
                records_path=("result", "records"),
                series_filter_field="series",
                series_filter_value="Target",
                wide_period_pattern=r"\d{4}[A-Za-z]{3}",
                unit_scale=Decimal("100"),
            )
            plan, series = _make_plan(path, mapping)

            rows = normalize_series(plan, series)

            self.assertEqual([item.period for item in rows], ["2026-01", "2026-02"])
            self.assertEqual(rows[0].value, Decimal("120.0"))

    def test_schema_drift_raises_mapping_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "series.csv"
            path.write_text("new_date,new_value\n2026-01,1\n", encoding="utf-8")
            mapping = MappingContract(
                contract_version="1",
                source_id="test_source",
                series_id="test_index",
                source_format="csv",
                layout="long",
                date_field="period",
                value_field="value",
            )
            plan, series = _make_plan(path, mapping)

            with self.assertRaises(MappingFailure):
                normalize_series(plan, series)

    def test_duplicate_without_revision_policy_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "series.csv"
            path.write_text(
                "period,value\n2026-01,1\n2026-01,2\n",
                encoding="utf-8",
            )
            mapping = MappingContract(
                contract_version="1",
                source_id="test_source",
                series_id="test_index",
                source_format="csv",
                layout="long",
                date_field="period",
                value_field="value",
            )
            plan, series = _make_plan(path, mapping)
            rows = normalize_series(plan, series)

            _, result = validate_series(rows, series)

            self.assertEqual(result.status, "fail")
            self.assertIn("UNEXPLAINED_DUPLICATE", {item.code for item in result.issues})


if __name__ == "__main__":
    unittest.main()
