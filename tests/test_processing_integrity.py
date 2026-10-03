from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from housing_agent.onboarding.discovery_models import (
    AggregationMethod,
    ChangeMethod,
    SeriesType,
)
from housing_agent.preparation.models import (
    ChangeCalculation,
    PreparationContract,
    QuarterlyComparisonView,
)
from housing_agent.processing.integrity import verify_frozen_data_plan
from housing_agent.processing.models import (
    FrozenDataPlan,
    FrozenSeriesPlan,
    MappingContract,
)


def _preparation(source_id: str, predictor_id: str, frequency: str) -> PreparationContract:
    quarterly = None
    input_view = "native"
    horizon = "yoy"
    lag = 4
    if frequency == "monthly":
        quarterly = QuarterlyComparisonView(
            aggregation_method=AggregationMethod.MEAN,
            incomplete_period_policy="reject",
            rationale="Quarterly means represent the approved comparison view.",
        )
        input_view = "quarterly_comparison"
    elif frequency == "annual":
        horizon = "period_change"
        lag = 1
    return PreparationContract(
        source_id=source_id,
        predictor_id=predictor_id,
        native_frequency=frequency,
        preserve_native_view=True,
        quarterly_comparison=quarterly,
        change_calculations=[ChangeCalculation(
            input_view=input_view,
            horizon=horizon,
            method=ChangeMethod.PERCENT,
            lag_periods=lag,
            rationale="This approved change supports comparable trend interpretation.",
        )],
        predictive_alignment=None,
        rationale="Preserve native observations and calculate only the approved trend view.",
        decision_basis=["human approval", "series semantics"],
    )


def _series(
    path: Path,
    source_id: str,
    series_id: str,
    market: str,
    portfolio_role: str = "outcome",
) -> FrozenSeriesPlan:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return FrozenSeriesPlan(
        source_id=source_id,
        series_id=series_id,
        series_label=f"{market.title()} outcome",
        snapshot_path=str(path),
        snapshot_sha256=digest,
        mapping_contract=MappingContract(
            contract_version="1",
            source_id=source_id,
            series_id=series_id,
            source_format="csv",
            layout="long",
            date_field="period",
            value_field="value",
            period_format="quarter",
        ),
        preparation_contract=_preparation(source_id, series_id, "quarterly"),
        definition="Official quarterly housing outcome index.",
        unit="index",
        observation_frequency="quarterly",
        update_frequency="quarterly",
        series_type=SeriesType.INDEX,
        portfolio_role=portfolio_role,
        market_role=market,
    )


def _plan(series: tuple[FrozenSeriesPlan, ...]) -> FrozenDataPlan:
    draft = FrozenDataPlan(
        plan_id="test_plan",
        plan_version=1,
        plan_sha256="0" * 64,
        approval_status="approved",
        approved_by="Test reviewer",
        approved_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        reporting_as_of_date=date(2026, 6, 30),
        historical_start_date=date(2020, 1, 1),
        historical_end_date=date(2026, 6, 30),
        series=series,
    )
    return draft.model_copy(update={"plan_sha256": draft.computed_sha256()})


class ProcessingIntegrityTests(unittest.TestCase):
    def test_approved_plan_and_snapshots_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sale = root / "sale.csv"
            rent = root / "rent.csv"
            predictor = root / "predictor.csv"
            sale.write_text("period,value\n2026-Q1,100\n", encoding="utf-8")
            rent.write_text("period,value\n2026-Q1,100\n", encoding="utf-8")
            predictor.write_text("period,value\n2026-Q1,4\n", encoding="utf-8")
            plan = _plan((
                _series(sale, "sale_source", "sale_index", "sale"),
                _series(rent, "rent_source", "rent_index", "rent"),
                _series(
                    predictor,
                    "predictor_source",
                    "predictor_index",
                    "shared",
                    "predictor",
                ),
            ))

            result = verify_frozen_data_plan(plan)

            self.assertEqual(result.status, "pass")
            self.assertEqual(result.verified_snapshot_count, 3)

    def test_checksum_mismatch_is_hard_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sale = root / "sale.csv"
            rent = root / "rent.csv"
            predictor = root / "predictor.csv"
            sale.write_text("period,value\n2026-Q1,100\n", encoding="utf-8")
            rent.write_text("period,value\n2026-Q1,100\n", encoding="utf-8")
            predictor.write_text("period,value\n2026-Q1,4\n", encoding="utf-8")
            plan = _plan((
                _series(sale, "sale_source", "sale_index", "sale"),
                _series(rent, "rent_source", "rent_index", "rent"),
                _series(
                    predictor,
                    "predictor_source",
                    "predictor_index",
                    "shared",
                    "predictor",
                ),
            ))
            sale.write_text("period,value\n2026-Q1,999\n", encoding="utf-8")

            result = verify_frozen_data_plan(plan)

            self.assertEqual(result.status, "fail")
            self.assertIn("RAW_CHECKSUM_MISMATCH", {item.code for item in result.issues})

    def test_missing_rent_outcome_routes_to_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sale = root / "sale.csv"
            predictor = root / "predictor.csv"
            sale.write_text("period,value\n2026-Q1,100\n", encoding="utf-8")
            predictor.write_text("period,value\n2026-Q1,4\n", encoding="utf-8")
            plan = _plan((
                _series(sale, "sale_source", "sale_index", "sale"),
                _series(
                    predictor,
                    "predictor_source",
                    "predictor_index",
                    "shared",
                    "predictor",
                ),
            ))

            result = verify_frozen_data_plan(plan)

            self.assertEqual(result.status, "recovery_required")
            self.assertIn("MISSING_OUTCOME", {item.code for item in result.issues})


if __name__ == "__main__":
    unittest.main()
