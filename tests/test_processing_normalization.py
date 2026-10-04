from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from housing_agent.onboarding.discovery_models import SeriesType
from housing_agent.processing.models import (
    DerivedSeriesContract,
    FrozenDataPlan,
    FrozenSeriesPlan,
    MappingContract,
)
from housing_agent.processing.normalization import (
    MappingFailure,
    normalize_series,
    normalize_series_with_trace,
)
from housing_agent.processing.policy_registry import DerivedOperation
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
    def test_ratio_is_derived_from_two_approved_raw_series_with_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "vacancy.json"
            raw.write_text(json.dumps({"result": {"records": [
                {"series": "Available", "20261Q": "1000", "20262Q": "1200"},
                {"series": "Vacant", "20261Q": "50", "20262Q": "72"},
            ]}}), encoding="utf-8")
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            source_id = "vacancy_source"
            series_id = "vacancy_rate"
            mapping = MappingContract(
                contract_version="1",
                source_id=source_id,
                series_id=series_id,
                source_format="json",
                layout="wide",
                records_path=("result", "records"),
                series_filter_field="series",
                series_filter_value="Available",
                wide_period_pattern=r"\d{5}Q",
            )
            series = FrozenSeriesPlan(
                source_id=source_id,
                series_id=series_id,
                series_label="Vacancy rate",
                snapshot_path=str(raw),
                snapshot_sha256=digest,
                mapping_contract=mapping,
                derived_series_contract=DerivedSeriesContract(
                    operation=DerivedOperation.RATIO,
                    input_series_filters={
                        "numerator": "Vacant",
                        "denominator": "Available",
                    },
                    scale=Decimal("100"),
                ),
                preparation_contract=_preparation(source_id, series_id, "quarterly"),
                definition="Share of available housing units that are vacant.",
                unit="percent",
                observation_frequency="quarterly",
                update_frequency="quarterly",
                series_type=SeriesType.RATE,
                portfolio_role="predictor",
                market_role="rent",
            )
            draft = FrozenDataPlan(
                plan_id="derived_ratio_test",
                plan_version=1,
                plan_sha256="0" * 64,
                approval_status="approved",
                approved_by="Test reviewer",
                approved_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
                reporting_as_of_date=date(2026, 6, 30),
                historical_start_date=date(2026, 1, 1),
                historical_end_date=date(2026, 6, 30),
                series=(series,),
            )
            plan = draft.model_copy(update={"plan_sha256": draft.computed_sha256()})

            rows, traces = normalize_series_with_trace(plan, series)

            self.assertEqual([item.value for item in rows], [Decimal("5.00"), Decimal("6.00")])
            self.assertTrue(all(item.derivation == "ratio of approved input series; scale=100" for item in rows))
            self.assertEqual(traces[0].operation, "derive_ratio")
            self.assertEqual(
                traces[0].parameters["input_series_filters"]["numerator"], "Vacant"
            )

    def test_derived_ratio_rejects_zero_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "vacancy.json"
            raw.write_text(json.dumps({"result": {"records": [
                {"series": "Available", "20261Q": "0"},
                {"series": "Vacant", "20261Q": "1"},
            ]}}), encoding="utf-8")
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            mapping = MappingContract(
                contract_version="1",
                source_id="vacancy_source",
                series_id="vacancy_rate",
                source_format="json",
                layout="wide",
                records_path=("result", "records"),
                series_filter_field="series",
                series_filter_value="Available",
                wide_period_pattern=r"\d{5}Q",
            )
            series = FrozenSeriesPlan(
                source_id="vacancy_source",
                series_id="vacancy_rate",
                series_label="Vacancy rate",
                snapshot_path=str(raw),
                snapshot_sha256=digest,
                mapping_contract=mapping,
                derived_series_contract=DerivedSeriesContract(
                    operation="ratio",
                    input_series_filters={"numerator": "Vacant", "denominator": "Available"},
                    scale=Decimal("100"),
                ),
                preparation_contract=_preparation("vacancy_source", "vacancy_rate", "quarterly"),
                definition="Share of available housing units that are vacant.",
                unit="percent",
                observation_frequency="quarterly",
                update_frequency="quarterly",
                series_type=SeriesType.RATE,
                portfolio_role="predictor",
                market_role="rent",
            )
            draft = FrozenDataPlan(
                plan_id="zero_denominator_test",
                plan_version=1,
                plan_sha256="0" * 64,
                approval_status="approved",
                approved_by="Test reviewer",
                approved_at=datetime(2026, 3, 31, tzinfo=timezone.utc),
                reporting_as_of_date=date(2026, 3, 31),
                historical_start_date=date(2026, 1, 1),
                historical_end_date=date(2026, 3, 31),
                series=(series,),
            )
            plan = draft.model_copy(update={"plan_sha256": draft.computed_sha256()})

            with self.assertRaisesRegex(MappingFailure, "zero denominator"):
                normalize_series(plan, series)

    def test_singstat_quarter_period_is_canonicalized(self) -> None:
        from housing_agent.processing.normalization import parse_period

        period, period_end = parse_period("20262Q", "quarterly")

        self.assertEqual(period, "2026-Q2")
        self.assertEqual(period_end.isoformat(), "2026-06-30")

    def test_multiple_approved_series_filters_select_one_exact_series(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "rental.json"
            raw.write_text(json.dumps({"result": {"records": [
                {"period": "2026-01", "type": "Non-Landed", "area": "Whole Island", "value": "100"},
                {"period": "2026-01", "type": "Non-Landed", "area": "Core", "value": "110"},
                {"period": "2026-01", "type": "Landed", "area": "Whole Island", "value": "90"},
            ]}}), encoding="utf-8")
            mapping = MappingContract(
                contract_version="1",
                source_id="rental_source",
                series_id="rental_index",
                source_format="json",
                layout="long",
                records_path=("result", "records"),
                date_field="period",
                value_field="value",
                series_filter_field="type",
                series_filter_value="Non-Landed",
                additional_series_filters={"area": "Whole Island"},
            )
            plan, series = _make_plan(raw, mapping)

            rows = normalize_series(plan, series)

            self.assertEqual(len(rows), 1)
            self.assertEqual(str(rows[0].value), "100")

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
