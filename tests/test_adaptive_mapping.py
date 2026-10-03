from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook

from housing_agent.onboarding.mapping_agent import (
    MAPPING_AGENT_INSTRUCTIONS,
    build_adaptive_mapping_graph,
    make_adaptive_mapping_node,
)
from housing_agent.onboarding.mapping_execution import execute_mapping
from housing_agent.onboarding.mapping_models import MappingProposal
from housing_agent.onboarding.schema_profiler import profile_snapshot
from housing_agent.preparation.models import RawSnapshotEvidence
from housing_agent.preparation.raw_capture import capture_unmapped_raw_snapshot
from housing_agent.processing.models import MappingContract
from housing_agent.onboarding.discovery_models import DiscoverySourceType
from housing_agent.onboarding.models import load_approved_catalog_entry
from tests.test_preparation_advisor import approved_source


def _proposal(*, value_field: str) -> MappingProposal:
    return MappingProposal(
        source_id="new_source",
        series_id="new_index",
        mapping_contract=MappingContract(
            contract_version="1",
            source_id="new_source",
            series_id="new_index",
            source_format="csv",
            layout="long",
            date_field="Observation Month",
            value_field=value_field,
        ),
        selected_table_location="csv:root",
        rationale="Use the exact monthly period and published index fields shown in the profile.",
        confidence="high",
        assumptions=[],
    )


class FakeMappingClient:
    def __init__(self, proposals: list[MappingProposal]) -> None:
        self.proposals = proposals
        self.inputs: list[str] = []

    def propose(self, *, instructions: str, input_text: str, model: str):
        self.inputs.append(input_text)
        proposal = self.proposals.pop(0)
        return proposal, {"proposal": proposal.model_dump(mode="json")}, {
            "provider": "fake",
            "model": model,
        }


def _snapshot(path: Path) -> RawSnapshotEvidence:
    body = path.read_bytes()
    return RawSnapshotEvidence(
        source_id="new_source",
        status="pass",
        retrieval_url="https://data.gov.sg/example.csv",
        retrieved_at=datetime.now(timezone.utc),
        http_status=200,
        content_type="text/csv",
        byte_count=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        snapshot_path=str(path),
        preview_records=[],
        errors=[],
    )


class AdaptiveMappingTests(unittest.TestCase):
    def test_mapping_prompt_treats_profile_samples_as_untrusted(self) -> None:
        self.assertIn("untrusted data", MAPPING_AGENT_INSTRUCTIONS)
        self.assertIn("Do not aggregate", MAPPING_AGENT_INSTRUCTIONS)

    def test_unmapped_excel_is_preserved_before_any_mapping_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workbook_path = Path(directory) / "input.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["Month", "Value"])
            sheet.append(["2026-01", 1.2])
            sheet.append(["2026-02", 1.3])
            workbook.save(workbook_path)
            body = workbook_path.read_bytes()
            approved = load_approved_catalog_entry(approved_source())
            approved = approved.model_copy(update={
                "entry": approved.entry.model_copy(update={
                    "source_type": DiscoverySourceType.XLSX,
                })
            })

            class FakeResponse:
                status = 200
                headers = {
                    "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                }

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

                def geturl(self):
                    return approved.entry.retrieval_url

                def read(self, size):
                    return body

            evidence = capture_unmapped_raw_snapshot(
                approved,
                snapshot_directory=Path(directory) / "raw",
                opener=lambda *args, **kwargs: FakeResponse(),
            )

            self.assertEqual(evidence.status, "pass")
            self.assertTrue(evidence.snapshot_path.endswith(".xlsx"))
            profile = profile_snapshot(
                source_id=evidence.source_id,
                snapshot_path=evidence.snapshot_path,
                snapshot_sha256=evidence.sha256,
            )
            self.assertEqual(profile.source_format, "xlsx")

    def test_full_snapshot_execution_reconciles_and_profiles_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.csv"
            path.write_text(
                "Observation Month,Published Index\n2026-01,100\n2026-02,101\n2026-03,-\n",
                encoding="utf-8",
            )
            profile = profile_snapshot(
                source_id="new_source",
                snapshot_path=path,
                snapshot_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )

            report = execute_mapping(
                proposal=_proposal(value_field="Published Index"),
                profile=profile,
                observation_frequency="monthly",
            )

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.extracted_observation_count, 3)
            self.assertEqual(report.parsed_observation_count, 3)
            self.assertEqual(report.non_null_observation_count, 2)
            self.assertEqual(report.missing_observation_count, 1)
            self.assertEqual(report.observed_period_start, "2026-01")
            self.assertEqual(report.observed_period_end, "2026-03")

    def test_invalid_first_mapping_is_repaired_from_deterministic_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.csv"
            path.write_text(
                "Observation Month,Published Index\n2026-01,100\n2026-02,101\n",
                encoding="utf-8",
            )
            client = FakeMappingClient([
                _proposal(value_field="Invented Value"),
                _proposal(value_field="Published Index"),
            ])
            node = make_adaptive_mapping_node(lambda provider: client)

            output = node({
                "source_context": {
                    "definition": "Official monthly index.",
                    "unit": "index points",
                },
                "source_id": "new_source",
                "series_id": "new_index",
                "observation_frequency": "monthly",
                "raw_snapshot_evidence": _snapshot(path).model_dump(mode="json"),
                "mapping_provider": "gemini",
                "max_mapping_attempts": 3,
                "mapping_artifact_dir": str(Path(directory) / "mapping"),
            })

            result = output["adaptive_mapping_result"]
            self.assertEqual(result["status"], "ready_for_human_review")
            self.assertEqual(len(result["attempts"]), 2)
            self.assertIn("absent", client.inputs[1])
            self.assertTrue((Path(directory) / "mapping" / "schema_profile.json").is_file())

    def test_recovery_stops_after_configured_maximum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.csv"
            path.write_text(
                "Observation Month,Published Index\n2026-01,100\n2026-02,101\n",
                encoding="utf-8",
            )
            client = FakeMappingClient([
                _proposal(value_field="Wrong A"),
                _proposal(value_field="Wrong B"),
                _proposal(value_field="Wrong C"),
            ])
            node = make_adaptive_mapping_node(lambda provider: client)

            output = node({
                "source_context": {"definition": "Official index."},
                "source_id": "new_source",
                "series_id": "new_index",
                "observation_frequency": "monthly",
                "raw_snapshot_evidence": _snapshot(path).model_dump(mode="json"),
                "mapping_provider": "gemini",
                "max_mapping_attempts": 3,
            })

            result = output["adaptive_mapping_result"]
            self.assertEqual(result["status"], "mapping_recovery_exhausted")
            self.assertEqual(len(result["attempts"]), 3)
            self.assertIsNone(result["accepted_proposal"])

    def test_isolated_langgraph_compiles_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.csv"
            path.write_text(
                "Observation Month,Published Index\n2026-01,100\n2026-02,101\n",
                encoding="utf-8",
            )
            client = FakeMappingClient([_proposal(value_field="Published Index")])
            graph = build_adaptive_mapping_graph(lambda provider: client)

            output = graph.invoke({
                "source_context": {"definition": "Official index."},
                "source_id": "new_source",
                "series_id": "new_index",
                "observation_frequency": "monthly",
                "raw_snapshot_evidence": _snapshot(path).model_dump(mode="json"),
                "mapping_provider": "gemini",
                "max_mapping_attempts": 3,
            })

            self.assertEqual(
                output["adaptive_mapping_result"]["status"],
                "ready_for_human_review",
            )


if __name__ == "__main__":
    unittest.main()
