from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from housing_agent.onboarding.discovery_models import DiscoverySourceType, SeriesType
from housing_agent.onboarding.mapping_execution import execute_mapping
from housing_agent.onboarding.mapping_agent import make_adaptive_mapping_node
from housing_agent.onboarding.mapping_models import (
    AdaptiveMappingResult,
    MappingAttempt,
    MappingProposal,
    SeriesRoleAssignment,
    UnifiedDataPlanReviewSubmission,
    UnifiedSourceDecision,
)
from housing_agent.onboarding.models import ApprovedCatalogEntry, load_approved_catalog_entry
from housing_agent.onboarding.plan_freezer import (
    build_unified_review_markdown,
    evaluate_and_freeze_data_plan,
)
from housing_agent.onboarding.schema_profiler import profile_snapshot
from housing_agent.preparation.models import PreparationContract, RawSnapshotEvidence
from housing_agent.processing.models import MappingContract, load_frozen_data_plan
from housing_agent.processing.pipeline import run_stage3
from tests.test_preparation_advisor import approved_source
from tests.test_processing_integrity import _preparation
from tests.test_processing_transformation import _contract as predictor_contract


def _catalog(source_id: str, series_id: str, frequency: str) -> ApprovedCatalogEntry:
    base = load_approved_catalog_entry(approved_source())
    entry = base.entry.model_copy(update={
        "source_id": source_id,
        "candidate_id": source_id,
        "predictor_id": series_id,
        "source_type": DiscoverySourceType.CSV,
        "definition": f"Official {frequency} series for {series_id}.",
        "unit": "index points",
        "native_frequency": frequency,
        "update_frequency": frequency,
        "series_type": SeriesType.INDEX,
    })
    return base.model_copy(update={"entry": entry})


def _snapshot(source_id: str, path: Path) -> RawSnapshotEvidence:
    body = path.read_bytes()
    return RawSnapshotEvidence(
        source_id=source_id,
        status="pass",
        retrieval_url="https://data.gov.sg/example.csv",
        retrieved_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
        http_status=200,
        content_type="text/csv",
        byte_count=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        snapshot_path=str(path),
        preview_records=[],
        errors=[],
    )


def _mapping_result(
    source_id: str, series_id: str, path: Path, frequency: str
) -> AdaptiveMappingResult:
    snapshot = _snapshot(source_id, path)
    profile = profile_snapshot(
        source_id=source_id,
        snapshot_path=path,
        snapshot_sha256=snapshot.sha256,
    )
    proposal = MappingProposal(
        source_id=source_id,
        series_id=series_id,
        mapping_contract=MappingContract(
            contract_version="1",
            source_id=source_id,
            series_id=series_id,
            source_format="csv",
            layout="long",
            date_field="Period Label",
            value_field="Published Level",
        ),
        selected_table_location="csv:root",
        rationale="Use the exact period label and published level fields in the profiled file.",
        confidence="high",
        assumptions=[],
    )
    execution = execute_mapping(
        proposal=proposal,
        profile=profile,
        observation_frequency=frequency,
    )
    return AdaptiveMappingResult(
        status="ready_for_human_review",
        source_id=source_id,
        series_id=series_id,
        schema_profile=profile,
        accepted_proposal=proposal,
        accepted_execution=execution,
        attempts=[MappingAttempt(
            attempt=1,
            proposal=proposal,
            execution=execution,
            provider_metadata={"provider": "fake"},
            error_feedback=[],
        )],
        errors=[],
    )


def _fixtures(root: Path):
    quarters = [
        "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"
    ]
    sale = root / "sale.csv"
    rent = root / "rent.csv"
    predictor = root / "predictor.csv"
    sale.write_text(
        "Period Label,Published Level\n"
        + "".join(f"{period},{100 + index}\n" for index, period in enumerate(quarters)),
        encoding="utf-8",
    )
    rent.write_text(
        "Period Label,Published Level\n"
        + "".join(f"{period},{90 + index}\n" for index, period in enumerate(quarters)),
        encoding="utf-8",
    )
    months = [f"{year}-{month:02d}" for year in (2025, 2026) for month in range(1, 13) if not (year == 2026 and month > 3)]
    predictor.write_text(
        "Period Label,Published Level\n"
        + "".join(f"{period},{70 + index}\n" for index, period in enumerate(months)),
        encoding="utf-8",
    )
    return sale, rent, predictor


def _bundle(root: Path):
    sale, rent, predictor = _fixtures(root)
    configs = [
        ("sale_source", "sale_index", sale, "quarterly", "sale", "outcome"),
        ("rent_source", "rent_index", rent, "quarterly", "rent", "outcome"),
        ("predictor_source", "shared_index", predictor, "monthly", "shared", "predictor"),
    ]
    catalogs = [_catalog(source, series, frequency) for source, series, _, frequency, _, _ in configs]
    snapshots = [_snapshot(source, path) for source, _, path, _, _, _ in configs]
    mappings = [_mapping_result(source, series, path, frequency) for source, series, path, frequency, _, _ in configs]
    preparations: list[PreparationContract] = [
        _preparation("sale_source", "sale_index", "quarterly"),
        _preparation("rent_source", "rent_index", "quarterly"),
        predictor_contract().model_copy(update={
            "source_id": "predictor_source",
            "predictor_id": "shared_index",
        }),
    ]
    decisions = [
        UnifiedSourceDecision(
            source_id=source,
            decision="approve",
            role_assignment=SeriesRoleAssignment(
                source_id=source,
                series_id=series,
                series_label=series.replace("_", " ").title(),
                portfolio_role=role,
                market_role=market,
            ),
            review_notes=[],
        )
        for source, series, _, _, market, role in configs
    ]
    submission = UnifiedDataPlanReviewSubmission(
        plan_id="adaptive_plan",
        plan_version=1,
        reviewer="Human reviewer",
        confirmation_status="confirmed",
        reporting_as_of_date=date(2026, 6, 30),
        historical_start_date=date(2025, 1, 1),
        historical_end_date=date(2026, 6, 30),
        minimum_quarterly_observations=2,
        source_decisions=decisions,
        overall_notes=["Approved after reviewing raw evidence and transformations."],
    )
    return catalogs, snapshots, mappings, preparations, submission


class PlanFreezerTests(unittest.TestCase):
    def test_source_replacement_decision_routes_without_freezing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalogs, snapshots, mappings, preparations, submission = _bundle(root)
            decisions = list(submission.source_decisions)
            decisions[2] = UnifiedSourceDecision(
                source_id="predictor_source",
                decision="replace_source",
                role_assignment=None,
                review_notes=["Use a different official representation."],
            )
            submission = submission.model_copy(update={"source_decisions": decisions})

            result, frozen = evaluate_and_freeze_data_plan(
                approved_sources=catalogs,
                snapshots=snapshots,
                mapping_results=mappings,
                preparation_contracts=preparations,
                submission=submission,
            )

            self.assertEqual(result.status, "replace_source")
            self.assertEqual(result.replacement_source_ids, ["predictor_source"])
            self.assertIsNone(frozen)

    def test_repaired_unseen_mapping_flows_through_freeze_into_stage3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalogs, snapshots, mappings, preparations, submission = _bundle(root)
            predictor_snapshot = next(
                item for item in snapshots if item.source_id == "predictor_source"
            )

            def proposal(value_field: str) -> MappingProposal:
                return MappingProposal(
                    source_id="predictor_source",
                    series_id="shared_index",
                    mapping_contract=MappingContract(
                        contract_version="1",
                        source_id="predictor_source",
                        series_id="shared_index",
                        source_format="csv",
                        layout="long",
                        date_field="Period Label",
                        value_field=value_field,
                    ),
                    selected_table_location="csv:root",
                    rationale="Use exact fields from this previously unseen preserved CSV profile.",
                    confidence="high",
                    assumptions=[],
                )

            class RepairingClient:
                def __init__(self):
                    self.proposals = [proposal("Incorrect Field"), proposal("Published Level")]

                def propose(self, **kwargs):
                    item = self.proposals.pop(0)
                    return item, {"proposal": item.model_dump(mode="json")}, {"provider": "fake"}

            mapping_output = make_adaptive_mapping_node(
                lambda provider: RepairingClient()
            )({
                "source_context": {
                    "definition": "Official shared monthly index.",
                    "unit": "index points",
                },
                "source_id": "predictor_source",
                "series_id": "shared_index",
                "observation_frequency": "monthly",
                "raw_snapshot_evidence": predictor_snapshot.model_dump(mode="json"),
                "mapping_provider": "gemini",
                "max_mapping_attempts": 3,
            })
            repaired = AdaptiveMappingResult.model_validate(
                mapping_output["adaptive_mapping_result"]
            )
            self.assertEqual(len(repaired.attempts), 2)
            mappings = [
                repaired if item.source_id == "predictor_source" else item
                for item in mappings
            ]

            review, frozen = evaluate_and_freeze_data_plan(
                approved_sources=catalogs,
                snapshots=snapshots,
                mapping_results=mappings,
                preparation_contracts=preparations,
                submission=submission,
                output_directory=root / "review",
            )
            self.assertEqual(review.status, "approved")
            stage3 = run_stage3(frozen, root / "stage3")
            self.assertEqual(stage3.status, "success")

    def test_confirmed_unified_review_freezes_plan_and_stage3_consumes_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalogs, snapshots, mappings, preparations, submission = _bundle(root)

            result, frozen = evaluate_and_freeze_data_plan(
                approved_sources=catalogs,
                snapshots=snapshots,
                mapping_results=mappings,
                preparation_contracts=preparations,
                submission=submission,
                output_directory=root / "review",
            )

            self.assertEqual(result.status, "approved")
            self.assertIsNotNone(frozen)
            loaded = load_frozen_data_plan(root / "review" / "frozen_data_plan.json")
            stage3 = run_stage3(loaded, root / "stage3")
            self.assertEqual(stage3.status, "success")
            self.assertTrue((root / "stage3" / "evidence" / "validated_evidence_bundle.json").is_file())

    def test_draft_review_cannot_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalogs, snapshots, mappings, preparations, submission = _bundle(root)
            submission = submission.model_copy(update={"confirmation_status": "draft"})

            result, frozen = evaluate_and_freeze_data_plan(
                approved_sources=catalogs,
                snapshots=snapshots,
                mapping_results=mappings,
                preparation_contracts=preparations,
                submission=submission,
            )

            self.assertEqual(result.status, "invalid")
            self.assertIsNone(frozen)

    def test_unified_review_table_contains_raw_mapping_and_preparation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalogs, snapshots, mappings, preparations, _ = _bundle(Path(directory))

            markdown = build_unified_review_markdown(
                approved_sources=catalogs,
                snapshots=snapshots,
                mapping_results=mappings,
                preparation_contracts=preparations,
            )

            self.assertIn("Raw snapshot", markdown)
            self.assertIn("Mapping", markdown)
            self.assertIn("Coverage", markdown)
            self.assertIn("quarterly=", markdown)


if __name__ == "__main__":
    unittest.main()
