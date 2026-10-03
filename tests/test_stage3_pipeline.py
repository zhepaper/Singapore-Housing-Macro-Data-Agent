from __future__ import annotations

import hashlib
import tempfile
import unittest
from unittest.mock import patch
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
    PredictiveAlignment,
    QuarterlyComparisonView,
)
from housing_agent.processing.models import FrozenDataPlan, FrozenSeriesPlan, MappingContract
from housing_agent.processing.pipeline import run_stage3
from tests.test_processing_integrity import _preparation


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _outcome(path: Path, market: str) -> FrozenSeriesPlan:
    source_id = f"{market}_source"
    series_id = f"{market}_index"
    return FrozenSeriesPlan(
        source_id=source_id,
        series_id=series_id,
        series_label=f"Private residential {market} index",
        snapshot_path=str(path),
        snapshot_sha256=_digest(path),
        mapping_contract=MappingContract(
            contract_version="1",
            source_id=source_id,
            series_id=series_id,
            source_format="csv",
            layout="long",
            date_field="period",
            value_field="value",
        ),
        preparation_contract=_preparation(source_id, series_id, "quarterly"),
        definition=f"Official quarterly private residential {market} index.",
        unit="index points",
        observation_frequency="quarterly",
        update_frequency="quarterly",
        series_type=SeriesType.INDEX,
        portfolio_role="outcome",
        market_role=market,
    )


def _predictor(path: Path) -> FrozenSeriesPlan:
    contract = PreparationContract(
        source_id="macro_source",
        predictor_id="macro_rate",
        native_frequency="monthly",
        preserve_native_view=True,
        quarterly_comparison=QuarterlyComparisonView(
            aggregation_method=AggregationMethod.MEAN,
            incomplete_period_policy="reject",
            rationale="Quarterly mean is the approved representation of the monthly index.",
        ),
        change_calculations=[ChangeCalculation(
            input_view="quarterly_comparison",
            horizon="qoq",
            method=ChangeMethod.PERCENT,
            lag_periods=1,
            rationale="Quarter-on-quarter percentage change describes index momentum.",
        )],
        predictive_alignment=PredictiveAlignment(
            lag_periods=1,
            rationale="Use a one-quarter lag so the predictor predates the outcome quarter.",
        ),
        rationale="Preserve the monthly series and use an approved lagged quarterly view.",
        decision_basis=["human approval", "publication timing"],
    )
    return FrozenSeriesPlan(
        source_id="macro_source",
        series_id="macro_rate",
        series_label="Shared macro index",
        snapshot_path=str(path),
        snapshot_sha256=_digest(path),
        mapping_contract=MappingContract(
            contract_version="1",
            source_id="macro_source",
            series_id="macro_rate",
            source_format="csv",
            layout="long",
            date_field="period",
            value_field="value",
        ),
        preparation_contract=contract,
        definition="Monthly macroeconomic index used for both housing markets.",
        unit="index points",
        observation_frequency="monthly",
        update_frequency="monthly",
        series_type=SeriesType.INDEX,
        portfolio_role="predictor",
        market_role="shared",
        release_lag_days=15,
    )


def _write_fixture_data(root: Path) -> tuple[Path, Path, Path]:
    quarters = [
        f"{year}-Q{quarter}"
        for year in (2024, 2025, 2026)
        for quarter in range(1, 5)
        if not (year == 2026 and quarter > 2)
    ]
    sale = root / "sale.csv"
    rent = root / "rent.csv"
    sale.write_text(
        "period,value\n" + "".join(f"{period},{100 + index}\n" for index, period in enumerate(quarters)),
        encoding="utf-8",
    )
    rent.write_text(
        "period,value\n" + "".join(f"{period},{90 + index * 2}\n" for index, period in enumerate(quarters)),
        encoding="utf-8",
    )
    macro = root / "macro.csv"
    months = [
        f"{year}-{month:02d}"
        for year in (2024, 2025, 2026)
        for month in range(1, 13)
        if not (year == 2026 and month > 3)
    ]
    macro.write_text(
        "period,value\n" + "".join(f"{period},{80 + index}\n" for index, period in enumerate(months)),
        encoding="utf-8",
    )
    return sale, rent, macro


def _plan(sale: Path, rent: Path, macro: Path) -> FrozenDataPlan:
    draft = FrozenDataPlan(
        plan_id="stage3_integration",
        plan_version=1,
        plan_sha256="0" * 64,
        approval_status="approved",
        approved_by="Integration reviewer",
        approved_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        reporting_as_of_date=date(2026, 6, 30),
        historical_start_date=date(2024, 1, 1),
        historical_end_date=date(2026, 6, 30),
        minimum_quarterly_observations=4,
        series=(_outcome(sale, "sale"), _outcome(rent, "rent"), _predictor(macro)),
    )
    return draft.model_copy(update={"plan_sha256": draft.computed_sha256()})


class Stage3PipelineTests(unittest.TestCase):
    def test_unexpected_program_error_is_persisted_as_hard_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan(*_write_fixture_data(root))
            output = root / "output"

            with patch(
                "housing_agent.processing.pipeline._run_stage3",
                side_effect=RuntimeError("unexpected failure"),
            ):
                result = run_stage3(plan, output)

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.recovery_route.value, "hard_stop")
            self.assertTrue((output / "validation" / "diagnostics.json").is_file())

    def test_full_run_persists_validated_evidence_and_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan(*_write_fixture_data(root))
            output = root / "output"

            result = run_stage3(plan, output)

            self.assertEqual(result.status, "success")
            self.assertTrue((output / "evidence" / "validated_evidence_bundle.json").is_file())
            self.assertTrue((output / "checkpoints" / "normalized.json").is_file())
            self.assertTrue((output / "checkpoints" / "cross_series_validated.json").is_file())
            self.assertFalse((output / "validation" / "diagnostics.json").exists())

    def test_repeated_runs_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan(*_write_fixture_data(root))
            first, second = root / "first", root / "second"

            first_result = run_stage3(plan, first)
            second_result = run_stage3(plan, second)

            self.assertEqual(first_result.status, "success")
            self.assertEqual(second_result.status, "success")
            first_files = {
                str(path.relative_to(first)): path.read_bytes()
                for path in first.rglob("*") if path.is_file()
            }
            second_files = {
                str(path.relative_to(second)): path.read_bytes()
                for path in second.rglob("*") if path.is_file()
            }
            self.assertEqual(first_files, second_files)


if __name__ == "__main__":
    unittest.main()
