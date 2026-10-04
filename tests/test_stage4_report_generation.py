from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from housing_agent.processing.pipeline import run_stage3
from housing_agent.memory.compiler import compile_memory
from housing_agent.memory.models import ApprovedPredictorMemory, DecisionEvent
from housing_agent.research.models import AnalyticalRole, MarketRole
from housing_agent.report_generation.composer import claim_sentence, compose_report
from housing_agent.report_generation.evidence import build_report_context
from housing_agent.report_generation.models import (
    LiteratureRecord,
    ReportBrief,
    SourceRecord,
    WriterOutput,
)
from housing_agent.report_generation.memory_bridge import report_brief_from_memory
from housing_agent.report_generation.pipeline import load_evidence_bundle, run_stage4
from housing_agent.report_generation.verification import verify_report
from housing_agent.report_generation.writer import DeterministicReportWriter
from tests.test_stage3_pipeline import _plan, _write_fixture_data


class AlwaysInvalidWriter:
    provider = "test-invalid"
    model = "invalid-writer"

    def __init__(self) -> None:
        self.calls = 0

    def write(self, context, *, attempt, feedback=()):
        self.calls += 1
        return WriterOutput(
            narrative="### Executive Summary\n\nUnsupported numerical claim: 999 percent.",
            provider=self.provider,
            model=self.model,
            prompt_version=context.prompt_version,
            attempt=attempt,
        )


class RepairingWriter:
    provider = "test-repair"
    model = "repairing-writer"

    def __init__(self) -> None:
        self.calls = 0

    def write(self, context, *, attempt, feedback=()):
        self.calls += 1
        if attempt == 1:
            narrative = "### Executive Summary\n\nUnsupported numerical claim: 999 percent."
        else:
            narrative = DeterministicReportWriter().write(
                context, attempt=attempt, feedback=feedback
            ).narrative
        return WriterOutput(
            narrative=narrative,
            provider=self.provider,
            model=self.model,
            prompt_version=context.prompt_version,
            attempt=attempt,
        )


class Stage4ReportGenerationTests(unittest.TestCase):
    def _stage3_bundle(self, root: Path):
        sale, rent, macro = _write_fixture_data(root)
        result = run_stage3(_plan(sale, rent, macro), root / "stage3")
        self.assertEqual(result.status, "success")
        assert result.evidence_bundle_path
        return load_evidence_bundle(result.evidence_bundle_path), (sale, rent, macro)

    def test_stage3_bundle_generates_verified_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            result = run_stage4(bundle, root / "stage4")

            self.assertEqual(result.status, "success")
            self.assertEqual(result.attempts, 1)
            report = Path(result.report_path or "").read_text(encoding="utf-8")
            self.assertIn("## Rental-Market Findings", report)
            self.assertIn("## Sale-Market Findings", report)
            self.assertIn("## Data and Analytical Approach", report)
            self.assertNotIn("## Validated Evidence", report)
            self.assertNotIn("| Indicator |", report)
            self.assertIn("**Information cut-off:** 2026-06-30", report)
            verification = json.loads(Path(result.verification_path or "").read_text())
            self.assertEqual(verification["status"], "pass")
            self.assertGreater(verification["claims_checked"], 0)

    def test_stage4_does_not_read_raw_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, snapshots = self._stage3_bundle(root)
            for path in snapshots:
                path.unlink()

            result = run_stage4(bundle, root / "stage4")

            self.assertEqual(result.status, "success")

    def test_predictive_lag_views_are_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            context = build_report_context(bundle)
            self.assertFalse(any("__predictive_lag_" in item.series_id for item in context.claims))
            self.assertTrue(any("__qoq_percent" in item.series_id for item in context.claims))

    def test_tampered_value_fails_exact_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            context = build_report_context(bundle)
            narrative = DeterministicReportWriter().write(context, attempt=1).narrative
            report = compose_report(context, narrative)
            first = context.claims[0]
            rendered = claim_sentence(first)
            tampered = report.replace(rendered, rendered.replace(first.value_text, "999", 1), 1)

            result = verify_report(tampered, context)

            self.assertEqual(result.status, "fail")
            self.assertTrue(any("altered deterministic evidence" in item for item in result.errors))

    def test_extra_unledgered_number_in_claim_block_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            context = build_report_context(bundle)
            narrative = DeterministicReportWriter().write(context, attempt=1).narrative
            report = compose_report(context, narrative)
            rendered = claim_sentence(context.claims[0])
            tampered = report.replace(rendered, rendered + " An unsupported 999 was added.", 1)

            result = verify_report(tampered, context)

            self.assertEqual(result.status, "fail")
            self.assertTrue(any("not rendered from the claim ledger" in item for item in result.errors))

    def test_source_records_are_rendered_and_ledgered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            brief = ReportBrief(source_records=(SourceRecord(
                source_id="sale_source",
                title="Official sale source",
                url="https://example.gov.sg/sale",
                publisher="Example Agency",
            ),))
            result = run_stage4(bundle, root / "stage4", brief=brief)
            report = Path(result.report_path or "").read_text(encoding="utf-8")

            self.assertEqual(result.status, "success")
            self.assertIn("https://example.gov.sg/sale", report)
            ledger = json.loads((root / "stage4" / "claim_ledger.json").read_text())
            sale_claims = [item for item in ledger if item["source_id"] == "sale_source"]
            self.assertTrue(all(item["source_url"] for item in sale_claims))

    def test_revision_succeeds_without_reprocessing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            writer = RepairingWriter()

            result = run_stage4(bundle, root / "stage4", writer=writer)

            self.assertEqual(result.status, "success")
            self.assertEqual(result.attempts, 2)
            self.assertEqual(writer.calls, 2)
            manifest = json.loads((root / "stage4" / "report_prompt_manifest.json").read_text())
            self.assertEqual(len(manifest["attempts"]), 2)
            self.assertTrue((root / "stage4" / "prompts" / "attempt_1.txt").is_file())
            self.assertTrue((root / "stage4" / "prompts" / "attempt_2.txt").is_file())

    def test_three_failed_drafts_produce_blocked_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            writer = AlwaysInvalidWriter()

            result = run_stage4(bundle, root / "stage4", writer=writer)

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.attempts, 3)
            self.assertEqual(writer.calls, 3)
            self.assertTrue((root / "stage4" / "blocked_report.md").is_file())
            self.assertFalse((root / "stage4" / "final_report.md").exists())

    def test_prompt_and_manifest_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            result = run_stage4(bundle, root / "stage4")

            self.assertEqual(result.status, "success")
            prompt = (root / "stage4" / "report_prompt.txt").read_text()
            manifest = json.loads((root / "stage4" / "report_prompt_manifest.json").read_text())
            self.assertIn("exact anchor", prompt)
            self.assertIn("Do not write any other digits", prompt)
            self.assertIn("## Rental-Market Findings", prompt)
            self.assertEqual(manifest["evidence_sha256"], build_report_context(bundle).evidence_sha256)

    def test_rationale_citations_are_rendered_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, _ = self._stage3_bundle(root)
            brief = ReportBrief(
                predictor_rationales={"macro_source": "Macro conditions may affect both markets."},
                rationale_reference_ids={"macro_source": ("LIT-MACRO",)},
                literature_records=(LiteratureRecord(
                    reference_id="LIT-MACRO",
                    citation="Example academic source",
                    url="https://example.edu/paper",
                ),),
            )

            result = run_stage4(bundle, root / "stage4", brief=brief)
            report = Path(result.report_path or "").read_text(encoding="utf-8")

            self.assertEqual(result.status, "success")
            self.assertIn("Macro conditions may affect both markets.", report)
            self.assertIn("Example academic source", report)
            self.assertIn("https://example.edu/paper", report)

    def test_confirmed_memory_and_frozen_plan_populate_report_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, snapshots = self._stage3_bundle(root)
            events = [
                DecisionEvent.model_validate_json(line)
                for line in (Path(__file__).resolve().parents[1] / "config" / "project_memory.seed.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            memory, _ = compile_memory(events)
            macro = ApprovedPredictorMemory(
                predictor_id="macro_rate",
                selection_rationale=["Approved macro rationale carried through memory."],
                intended_market_role=MarketRole.SHARED,
                intended_analytical_role=AnalyticalRole.TIMELY_PREDICTOR,
                review_version=1,
            )
            memory = memory.model_copy(update={
                "approved_predictors": [*memory.approved_predictors, macro]
            })
            plan = _plan(*snapshots)

            brief = report_brief_from_memory(memory, plan=plan)
            context = build_report_context(bundle, brief)

            macro_claims = [item for item in context.claims if item.source_id == "macro_source"]
            self.assertTrue(macro_claims)
            self.assertTrue(all(
                item.rationale == "Approved macro rationale carried through memory."
                for item in macro_claims
            ))
            self.assertIn("Singapore", context.scope_summary)


if __name__ == "__main__":
    unittest.main()
