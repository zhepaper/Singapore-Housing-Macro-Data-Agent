from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from housing_agent.onboarding.discovery_models import AggregationMethod, ChangeMethod
from housing_agent.preparation.models import (
    ChangeCalculation,
    PreparationContract,
    PredictiveAlignment,
    QuarterlyComparisonView,
)
from housing_agent.processing.models import MappingContract
from housing_agent.processing.normalization import normalize_series
from housing_agent.processing.transformation import transform_series
from tests.test_processing_normalization import _make_plan


def _contract() -> PreparationContract:
    return PreparationContract(
        source_id="test_source",
        predictor_id="test_index",
        native_frequency="monthly",
        preserve_native_view=True,
        quarterly_comparison=QuarterlyComparisonView(
            aggregation_method=AggregationMethod.MEAN,
            incomplete_period_policy="reject",
            rationale="Complete-quarter means are the approved comparison representation.",
        ),
        change_calculations=[ChangeCalculation(
            input_view="quarterly_comparison",
            horizon="qoq",
            method=ChangeMethod.PERCENT,
            lag_periods=1,
            rationale="Quarter-on-quarter percentage change is approved for this index.",
        )],
        predictive_alignment=PredictiveAlignment(
            lag_periods=1,
            rationale="Align the predictor with the following quarter outcome for exploration.",
        ),
        rationale="Preserve monthly data and create an approved quarterly analytical view.",
        decision_basis=["human approval", "index semantics"],
    )


class ProcessingTransformationTests(unittest.TestCase):
    def test_reject_policy_excludes_incomplete_quarter_without_aborting_series(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "series.csv"
            path.write_text("period,value\n2026-01,1.0\n2026-02,1.1\n", encoding="utf-8")
            mapping = MappingContract(
                contract_version="1",
                source_id="test_source",
                series_id="test_index",
                source_format="csv",
                layout="long",
                date_field="period",
                value_field="value",
            )
            plan, base_series = _make_plan(path, mapping)
            series = base_series.model_copy(update={"preparation_contract": _contract()})
            incomplete = normalize_series(plan, series)

            output, trace = transform_series(incomplete, series)

            self.assertEqual(output, [])
            self.assertEqual(trace[0].operation, "incomplete_period_excluded")
            self.assertEqual(trace[0].output_period, "2026-Q1")

    def test_approved_mean_change_and_lag_are_calendar_based(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "series.csv"
            path.write_text(
                "period,value\n"
                "2025-10,100\n2025-11,101\n2025-12,102\n"
                "2026-01,102\n2026-02,103\n2026-03,105\n",
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
            plan, base_series = _make_plan(path, mapping)
            plan = plan.model_copy(update={"historical_start_date": plan.historical_start_date.replace(year=2025)})
            series = base_series.model_copy(update={"preparation_contract": _contract()})
            rows = normalize_series(plan, series)

            transformed, trace = transform_series(rows, series)

            quarterly = [item for item in transformed if item.series_id.endswith("__quarterly_mean")]
            changes = [item for item in transformed if "qoq_percentage_change" in item.series_id]
            lagged = [item for item in transformed if "predictive_lag_1" in item.series_id]
            self.assertEqual([item.period for item in quarterly], ["2025-Q4", "2026-Q1"])
            self.assertEqual(str(quarterly[0].value), "101")
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0].source_periods, ("2025-Q4", "2026-Q1"))
            self.assertEqual([item.period for item in lagged], ["2026-Q1", "2026-Q2"])
            self.assertTrue(any(item.operation == "calendar_lag" for item in trace))

    def test_missing_calendar_predecessor_is_not_used_as_previous_row(self) -> None:
        contract = _contract().model_copy(update={
            "quarterly_comparison": None,
            "predictive_alignment": None,
            "change_calculations": [ChangeCalculation(
                input_view="native",
                horizon="mom",
                method=ChangeMethod.PERCENT,
                lag_periods=1,
                rationale="Month-on-month percentage change requires adjacent months.",
            )],
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "series.csv"
            path.write_text("period,value\n2026-01,100\n2026-03,110\n", encoding="utf-8")
            mapping = MappingContract(
                contract_version="1",
                source_id="test_source",
                series_id="test_index",
                source_format="csv",
                layout="long",
                date_field="period",
                value_field="value",
            )
            plan, base_series = _make_plan(path, mapping)
            series = base_series.model_copy(update={"preparation_contract": contract})
            rows = normalize_series(plan, series)

            transformed, _ = transform_series(rows, series)

            self.assertEqual(transformed, [])


if __name__ == "__main__":
    unittest.main()
