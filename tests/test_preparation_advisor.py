import json
import tempfile
import unittest
from pathlib import Path

from housing_agent.memory.compiler import compile_memory
from housing_agent.memory.store import DecisionLogStore
from housing_agent.models import Observation
from housing_agent.preparation.advisor import (
    PreparationStructuredOutputError,
    build_preparation_input,
    build_data_preparation_advisor_graph,
    make_data_preparation_advisor_node,
)
from housing_agent.onboarding.mapping_models import MappingExecutionReport
from housing_agent.preparation.execution import execute_preparation_contract
from housing_agent.preparation.models import (
    DataPreparationProposal,
    PreparationContract,
    RawSnapshotEvidence,
)
from housing_agent.preparation.review import preparation_review_node
from housing_agent.preparation.raw_capture import capture_raw_snapshot
from housing_agent.onboarding.models import load_approved_catalog_entry
from tests.test_catalog_review import draft_entries


def memory_bundle():
    events = DecisionLogStore(Path("config/project_memory.seed.jsonl")).load()
    return compile_memory(events)


def approved_source() -> dict:
    entry = draft_entries()[0]
    entry["predictor_id"] = "three_month_compounded_sora"
    return {
        "catalog_version": "source-1",
        "approved_by": "human_reviewer",
        "approved_at": "2026-10-02T09:00:00Z",
        "entry": entry,
    }


def contract_dict(*, aggregation="last", incomplete="mark_partial") -> dict:
    return {
        "source_id": "sora_singstat_datagov",
        "predictor_id": "three_month_compounded_sora",
        "native_frequency": "monthly",
        "preserve_native_view": True,
        "quarterly_comparison": {
            "target_frequency": "quarterly",
            "aggregation_method": aggregation,
            "incomplete_period_policy": incomplete,
            "rationale": "Quarter-end values represent financing conditions at each quarter boundary.",
        },
        "change_calculations": [
            {
                "input_view": "native",
                "horizon": "mom",
                "method": "basis_point_change",
                "lag_periods": 1,
                "rationale": "Monthly basis-point changes retain the native rate signal.",
            },
            {
                "input_view": "quarterly_comparison",
                "horizon": "qoq",
                "method": "basis_point_change",
                "lag_periods": 1,
                "rationale": "Quarter-on-quarter basis-point changes match quarterly outcomes.",
            },
        ],
        "predictive_alignment": {
            "target_outcome_frequency": "quarterly",
            "lag_periods": 1,
            "interpretation": "exploratory_predictive_alignment",
            "rationale": "A one-quarter lag is retained only as an exploratory predictive view.",
        },
        "missing_value_policy": "preserve_null",
        "interpolation_allowed": False,
        "rationale": "Preserve monthly SORA and add a separately labelled quarter-end comparison view.",
        "decision_basis": [
            "memory_event:predictor_approval_001",
            "source_profile:sora_singstat_datagov",
        ],
    }


def proposal_dict() -> dict:
    memory, manifest = memory_bundle()
    return {
        "project_id": memory.project_id,
        "memory_version": memory.memory_version,
        "memory_sha256": manifest.snapshot_sha256,
        "structured_data_overview": (
            "The approved source is a monthly end-of-period percentage rate. Its native "
            "observations remain intact and any quarterly representation is a derived view."
        ),
        "concise_recommendation": (
            "Preserve monthly SORA and use a quarter-end quarterly view with basis-point "
            "changes for comparison with quarterly private housing outcomes."
        ),
        "recommendations": [{
            "source_profile_summary": (
                "SORA is published monthly as a percentage rate with month-end observations."
            ),
            "market_use_summary": (
                "The rate is a sale-focused financing proxy and is not direct evidence of rents."
            ),
            "contract": contract_dict(),
            "alternatives_considered": [
                "A quarterly mean would represent average conditions instead of quarter-end conditions."
            ],
            "limitations": [
                "SORA is a benchmark rate and not an observed mortgage borrowing rate."
            ],
        }],
        "unresolved_questions": [],
        "proposal_limitations": [
            "The recommended lag is exploratory and does not establish causality."
        ],
    }


def raw_snapshot_evidence() -> list[dict]:
    return [{
        "source_id": "sora_singstat_datagov",
        "status": "pass",
        "retrieval_url": approved_source()["entry"]["retrieval_url"],
        "retrieved_at": "2026-10-02T10:00:00Z",
        "http_status": 200,
        "content_type": "application/json",
        "byte_count": 1024,
        "sha256": "a" * 64,
        "snapshot_path": "outputs/test/raw/sora.json",
        "preview_records": [
            {"period": "2026Jun", "value": "2.11"},
            {"period": "2026May", "value": "2.18"},
        ],
        "errors": [],
    }]


class FakeAdvisorClient:
    def __init__(self):
        self.calls = []

    def advise(self, **kwargs):
        self.calls.append(kwargs)
        return (
            DataPreparationProposal.model_validate(proposal_dict()),
            {"id": "advisor-test"},
            {"provider": "fake", "model": kwargs["model"]},
        )


def observations(months=6):
    return [
        Observation(
            source_id="sora_singstat_datagov",
            series_id="sora_3m",
            series_label="Three-month compounded SORA",
            period=f"2026-{month:02d}",
            frequency="monthly",
            value=3.0 - month * 0.1,
            unit="percent per annum",
            market="sale",
            role="predictor",
            observation_status="observed",
        )
        for month in range(1, months + 1)
    ]


class PreparationAdvisorTests(unittest.TestCase):
    def test_advisor_input_uses_validated_full_snapshot_mapping_coverage(self):
        memory, manifest = memory_bundle()
        mapped = MappingExecutionReport(
            source_id="sora_singstat_datagov",
            series_id="sora_3m",
            status="pass",
            selected_record_count=1,
            extracted_observation_count=250,
            parsed_observation_count=250,
            non_null_observation_count=249,
            missing_observation_count=1,
            duplicate_periods=[],
            observed_period_start="2005-10",
            observed_period_end="2026-07",
            observations=[],
            errors=[],
            warnings=[],
        )

        text = build_preparation_input(
            memory,
            manifest,
            [load_approved_catalog_entry(approved_source())],
            [RawSnapshotEvidence.model_validate(raw_snapshot_evidence()[0])],
            [mapped],
        )

        self.assertIn("full_preserved_snapshot", text)
        self.assertIn('"non_null_observation_count": 249', text)
        self.assertIn("DETERMINISTIC FULL-SNAPSHOT MAPPING EXECUTION", text)

    def test_raw_capture_saves_reproducible_response_and_preview(self):
        body = json.dumps({
            "result": {
                "records": [{
                    "DataSeries": "Compounded Singapore Overnight Rate Average (SORA) - 3 Month",
                    "2026Apr": "2.30",
                    "2026May": "2.18",
                    "2026Jun": "2.11",
                }]
            }
        }).encode()

        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def geturl(self):
                return approved_source()["entry"]["retrieval_url"]

            def read(self, size):
                return body

        with tempfile.TemporaryDirectory() as temporary:
            evidence = capture_raw_snapshot(
                load_approved_catalog_entry(approved_source()),
                snapshot_directory=Path(temporary),
                opener=lambda *args, **kwargs: FakeResponse(),
            )
            self.assertEqual(evidence.status, "pass")
            self.assertTrue(Path(evidence.snapshot_path).is_file())
            self.assertEqual(evidence.preview_records[0]["period"], "2026Jun")
            self.assertEqual(evidence.observed_period_start, "2026Apr")
            self.assertEqual(evidence.observed_period_end, "2026Jun")
            self.assertEqual(evidence.non_null_observation_count, 3)
            self.assertEqual(len(evidence.sha256), 64)

    def test_schema_failure_receives_one_bounded_feedback_retry(self):
        class RetryClient:
            def __init__(self):
                self.inputs = []

            def advise(self, **kwargs):
                self.inputs.append(kwargs["input_text"])
                if len(self.inputs) == 1:
                    raise PreparationStructuredOutputError(
                        "missing_value_policy used a paraphrase",
                        raw={"attempt": 1},
                        metadata={"provider": "fake"},
                    )
                return DataPreparationProposal.model_validate(proposal_dict()), {"attempt": 2}, {"provider": "fake"}

        memory, manifest = memory_bundle()
        client = RetryClient()
        result = make_data_preparation_advisor_node(lambda: client)({
            "memory_snapshot": memory.model_dump(mode="json"),
            "memory_manifest": manifest.model_dump(mode="json"),
            "approved_catalog_entries": [approved_source()],
            "raw_snapshot_evidence": raw_snapshot_evidence(),
            "max_preparation_attempts": 2,
        })
        self.assertEqual(result["preparation_validation"]["automated_validation_status"], "pass")
        self.assertEqual(len(client.inputs), 2)
        self.assertIn("PREVIOUS RESPONSE FAILED THE TYPED SCHEMA", client.inputs[1])

    def test_isolated_advisor_langgraph_compiles_and_runs(self):
        memory, manifest = memory_bundle()
        result = build_data_preparation_advisor_graph(
            lambda: FakeAdvisorClient()
        ).invoke({
            "memory_snapshot": memory.model_dump(mode="json"),
            "memory_manifest": manifest.model_dump(mode="json"),
            "approved_catalog_entries": [approved_source()],
            "raw_snapshot_evidence": raw_snapshot_evidence(),
        })
        self.assertEqual(
            result["preparation_validation"]["human_review_status"], "pending"
        )

    def test_advisor_uses_memory_and_verified_source_then_waits_for_human(self):
        memory, manifest = memory_bundle()
        client = FakeAdvisorClient()
        with tempfile.TemporaryDirectory() as temporary:
            result = make_data_preparation_advisor_node(lambda: client)({
                "memory_snapshot": memory.model_dump(mode="json"),
                "memory_manifest": manifest.model_dump(mode="json"),
                "approved_catalog_entries": [approved_source()],
                "raw_snapshot_evidence": raw_snapshot_evidence(),
                "preparation_artifact_dir": temporary,
            })
            self.assertEqual(result["preparation_metadata"]["execution_status"], "success")
            self.assertEqual(result["preparation_validation"]["automated_validation_status"], "pass")
            self.assertEqual(result["preparation_validation"]["human_review_status"], "pending")
            self.assertIn("CONFIRMED PROJECT MEMORY", client.calls[0]["input_text"])
            self.assertTrue((Path(temporary) / "preparation_proposal.json").is_file())
            self.assertTrue((Path(temporary) / "preparation_review.md").is_file())
            markdown = (Path(temporary) / "preparation_review.md").read_text()
            self.assertIn("| Series | Market use |", markdown)
            self.assertIn("- [x] Raw response retrieved and preserved", markdown)
            self.assertIn("Provide my own preparation instructions", markdown)

    def test_advisor_requires_preserved_raw_evidence(self):
        memory, manifest = memory_bundle()
        result = make_data_preparation_advisor_node(lambda: FakeAdvisorClient())({
            "memory_snapshot": memory.model_dump(mode="json"),
            "memory_manifest": manifest.model_dump(mode="json"),
            "approved_catalog_entries": [approved_source()],
        })
        self.assertEqual(result["preparation_metadata"]["execution_status"], "fail")
        self.assertTrue(any("preserve raw snapshots" in item for item in result["preparation_errors"]))

    def test_rate_sum_is_rejected_deterministically(self):
        proposal = proposal_dict()
        proposal["recommendations"][0]["contract"]["quarterly_comparison"]["aggregation_method"] = "sum"

        class BadClient:
            def advise(self, **kwargs):
                return DataPreparationProposal.model_validate(proposal), {}, {}

        memory, manifest = memory_bundle()
        result = make_data_preparation_advisor_node(lambda: BadClient())({
            "memory_snapshot": memory.model_dump(mode="json"),
            "memory_manifest": manifest.model_dump(mode="json"),
            "approved_catalog_entries": [approved_source()],
            "raw_snapshot_evidence": raw_snapshot_evidence(),
        })
        self.assertEqual(result["preparation_validation"]["automated_validation_status"], "fail")
        self.assertTrue(any("Rates cannot be summed" in item for item in result["preparation_validation"]["errors"]))

    def test_human_review_writes_approved_contract_to_memory_idempotently(self):
        memory, manifest = memory_bundle()
        advisor = make_data_preparation_advisor_node(lambda: FakeAdvisorClient())({
            "memory_snapshot": memory.model_dump(mode="json"),
            "memory_manifest": manifest.model_dump(mode="json"),
            "approved_catalog_entries": [approved_source()],
            "raw_snapshot_evidence": raw_snapshot_evidence(),
        })
        submission = {
            "plan_version": "preparation-1",
            "reviewer": "human_reviewer",
            "review_choice": "approve_all",
            "custom_instructions": None,
            "confirmation_status": "confirmed",
            "source_reviews": [{
                "source_id": "sora_singstat_datagov",
                "decision": "approve",
                "approved_contract": contract_dict(),
                "review_notes": ["Approved as a distinct native and quarterly view."],
            }],
            "overall_notes": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "memory.jsonl"
            log.write_text(Path("config/project_memory.seed.jsonl").read_text())
            state = {
                "preparation_proposal": advisor["preparation_proposal"],
                "preparation_validation": advisor["preparation_validation"],
                "approved_catalog_entries": [approved_source()],
                "preparation_review_submission": submission,
                "memory_decision_log_path": str(log),
            }
            first = preparation_review_node(state)
            second = preparation_review_node(state)
            self.assertEqual(first["preparation_review_result"]["review_status"], "approved")
            self.assertEqual(len(DecisionLogStore(log).load()), 8)
            compiled, _ = compile_memory(DecisionLogStore(log).load())
            self.assertEqual(len(compiled.approved_preparation_plans), 1)
            self.assertEqual(
                compiled.approved_preparation_plans[0].quarterly_aggregation_method,
                "last",
            )
            self.assertEqual(
                first["preparation_memory_event"]["event_id"],
                second["preparation_memory_event"]["event_id"],
            )

    def test_custom_instructions_can_modify_contract_only_after_confirmation(self):
        memory, manifest = memory_bundle()
        advisor = make_data_preparation_advisor_node(lambda: FakeAdvisorClient())({
            "memory_snapshot": memory.model_dump(mode="json"),
            "memory_manifest": manifest.model_dump(mode="json"),
            "approved_catalog_entries": [approved_source()],
            "raw_snapshot_evidence": raw_snapshot_evidence(),
        })
        modified = contract_dict(aggregation="mean")
        submission = {
            "plan_version": "preparation-custom-1",
            "reviewer": "human_reviewer",
            "review_choice": "custom_instructions",
            "custom_instructions": "Use quarterly mean SORA instead of quarter-end SORA.",
            "confirmation_status": "confirmed",
            "source_reviews": [{
                "source_id": "sora_singstat_datagov",
                "decision": "approve",
                "approved_contract": modified,
                "review_notes": ["The approved contract reflects the user's instruction."],
            }],
            "overall_notes": [],
        }
        result = preparation_review_node({
            "preparation_proposal": advisor["preparation_proposal"],
            "preparation_validation": advisor["preparation_validation"],
            "approved_catalog_entries": [approved_source()],
            "preparation_review_submission": submission,
        })
        self.assertEqual(result["preparation_review_result"]["review_status"], "approved")
        self.assertEqual(
            result["approved_preparation_contracts"][0]["quarterly_comparison"]["aggregation_method"],
            "mean",
        )

        submission["confirmation_status"] = "draft"
        draft = preparation_review_node({
            "preparation_proposal": advisor["preparation_proposal"],
            "preparation_validation": advisor["preparation_validation"],
            "approved_catalog_entries": [approved_source()],
            "preparation_review_submission": submission,
        })
        self.assertEqual(draft["preparation_review_result"]["review_status"], "invalid")

    def test_deterministic_executor_preserves_native_and_labels_derived_views(self):
        output, trace = execute_preparation_contract(
            observations(), PreparationContract.model_validate(contract_dict())
        )
        self.assertEqual(trace.native_observations, 6)
        self.assertEqual(trace.comparison_observations, 2)
        self.assertEqual(trace.change_observations, 6)
        self.assertEqual(trace.output_observations, 16)
        native = [item for item in output if item.role == "predictor"]
        self.assertEqual(len(native), 6)
        self.assertTrue(any("quarterly_last" in item.series_id for item in output))
        self.assertTrue(any("predictive_lag_1" in item.series_id for item in output))

    def test_reject_policy_stops_incomplete_quarter(self):
        contract = PreparationContract.model_validate(
            contract_dict(incomplete="reject")
        )
        with self.assertRaisesRegex(ValueError, "Incomplete quarter"):
            execute_preparation_contract(observations(months=2), contract)


if __name__ == "__main__":
    unittest.main()
