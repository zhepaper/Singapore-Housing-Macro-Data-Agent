import unittest
import json
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from jsonschema import Draft202012Validator, FormatChecker

from housing_agent.reporting import DeterministicWriter, LangChainWriter, compose_report
from housing_agent.verification import verify_report
from housing_agent.workflow import route_after_verification, route_after_writer, writer_node


def evidence_fixture():
    base = {
        "source_id": "source",
        "series_label": "Rental index (qoq_pct)",
        "market": "rent",
        "period": "2026-Q2",
        "value": 0.5,
        "unit": "percent",
        "factor": "rent_market_benchmark",
        "definition": "Rental benchmark definition.",
        "series_identifier": "example-series",
        "observation_frequency": "quarterly",
        "update_frequency": "quarterly",
        "mechanism": "Describes rental-market movement.",
        "potential_lag": "Benchmark outcome.",
        "point_in_time_availability": "Current-vintage history.",
        "limitations": ["Employment flow, not population stock."],
        "source_page_url": "https://data.gov.sg/example",
        "source_observation_period": None,
        "completeness": "complete",
        "freshness_status": "current",
        "derivation": "(value / prior_value - 1) * 100",
        "source_periods": ["2026-Q1", "2026-Q2"],
        "input_series_ids": ["rental", "rental"],
    }
    return {"rental__qoq_pct": {"metric_id": "rental__qoq_pct", **base}}


class ReportingTests(unittest.TestCase):
    def test_deterministic_report_passes_verification(self):
        evidence = evidence_fixture()
        writer_result = DeterministicWriter().write(evidence)
        narrative = writer_result.narrative
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "schemas/writer-output.schema.json").read_text()
        )
        Draft202012Validator(schema, format_checker=FormatChecker()).validate({
            "narrative": writer_result.narrative, "metadata": writer_result.metadata,
        })
        report, ledger = compose_report(
            reporting_as_of_date="2026-10-01", narrative=narrative, evidence=evidence
        )
        result = verify_report(report, ledger, evidence)
        self.assertEqual(result["status"], "pass")
        self.assertIn("quarter on quarter", narrative)
        self.assertIn("Observation / update frequency", report)
        self.assertIn("Formula:", report)

    def test_tampered_claim_fails_verification(self):
        evidence = evidence_fixture()
        narrative = DeterministicWriter().write(evidence).narrative
        report, ledger = compose_report(
            reporting_as_of_date="2026-10-01", narrative=narrative, evidence=evidence
        )
        result = verify_report(report.replace("0.500 percent", "9.999 percent"), ledger, evidence)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("value" in error for error in result["errors"]))

    def test_numeric_llm_narrative_is_rejected(self):
        evidence = evidence_fixture()
        report, ledger = compose_report(
            reporting_as_of_date="2026-10-01",
            narrative="### Rental market\n\nRents increased by 8 percent.",
            evidence=evidence,
        )
        result = verify_report(report, ledger, evidence)
        self.assertIn("Writer narrative contains unsupported numeric text", result["errors"])

    def test_langchain_writer_uses_runnable(self):
        model = RunnableLambda(lambda messages: AIMessage(content=(
            "### Shared supply\n\nSupply expanded.\n\n"
            "### Rental market\n\nRental conditions tightened.\n\n"
            "### Sale market\n\nSale conditions softened."
        ), usage_metadata={"input_tokens": 10, "output_tokens": 8, "total_tokens": 18}))
        result = LangChainWriter(model).write(evidence_fixture())
        self.assertIn("Rental market", result.narrative)
        self.assertEqual(result.metadata["writer"], "langchain")
        self.assertEqual(result.metadata["token_usage"]["total_tokens"], 18)

    def test_openai_writer_without_key_routes_to_halt(self):
        with patch.dict("os.environ", {}, clear=True):
            result = writer_node({
                "writer_mode": "openai",
                "writer_model": "gpt-5-mini",
                "evidence": evidence_fixture(),
                "revision_count": 0,
            })
        self.assertIn("OPENAI_API_KEY", result["writer_error"])
        self.assertEqual(route_after_writer(result), "halt")

    def test_verification_revision_loop_is_bounded(self):
        self.assertEqual(route_after_verification({
            "verification_result": {"status": "fail"}, "revision_count": 1, "max_revisions": 2,
        }), "writer")
        self.assertEqual(route_after_verification({
            "verification_result": {"status": "fail"}, "revision_count": 2, "max_revisions": 2,
        }), "halt")

    def test_missing_market_heading_is_rejected(self):
        evidence = evidence_fixture()
        report, ledger = compose_report(
            reporting_as_of_date="2026-10-01",
            narrative="### Rental market\n\nConditions tightened.",
            evidence=evidence,
        )
        result = verify_report(report, ledger, evidence)
        self.assertTrue(any("missing required heading" in error for error in result["errors"]))

    def test_unledgered_quantitative_statement_is_rejected(self):
        evidence = evidence_fixture()
        narrative = DeterministicWriter().write(evidence).narrative
        report, ledger = compose_report(
            reporting_as_of_date="2026-10-01", narrative=narrative, evidence=evidence
        )
        report = report.replace("## Limitations", "- Untracked value: 123 percent.\n\n## Limitations")
        result = verify_report(report, ledger, evidence)
        self.assertTrue(any("no claim-ledger marker" in error for error in result["errors"]))

    def test_sale_rent_mechanism_confusion_is_rejected(self):
        evidence = evidence_fixture()
        narrative = (
            "### Shared supply\n\nSupply was stable.\n\n"
            "### Rental market\n\nSORA financing conditions softened.\n\n"
            "### Sale market\n\nSale conditions were stable."
        )
        report, ledger = compose_report(
            reporting_as_of_date="2026-10-01", narrative=narrative, evidence=evidence
        )
        result = verify_report(report, ledger, evidence)
        self.assertTrue(any("sale-specific mechanism" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
