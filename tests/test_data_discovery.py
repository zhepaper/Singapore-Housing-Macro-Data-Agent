import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from housing_agent.onboarding.discovery import (
    DataDiscoveryProposal,
    build_draft_entries,
    make_data_discovery_node,
    validate_discovery,
)
from housing_agent.onboarding.discovery_models import DataSourceCandidate, SourceProbeResult
from housing_agent.onboarding.discovery_models import load_discovery_proposal
from housing_agent.onboarding.discovery_tools import probe_data_source
from housing_agent.research.models import ApprovedResearchScope, ResearchProposal
from tests.test_research_search_node import approved_scope, valid_proposal_dict


def sora_candidate() -> dict:
    return {
        "candidate_id": "sora_singstat_datagov",
        "predictor_id": "financial_predictor_1",
        "official_agency": "Singapore Department of Statistics and MAS",
        "dataset_title": "Domestic Interest Rates",
        "source_type": "datagov_json",
        "source_page_url": "https://data.gov.sg/datasets/sora/view",
        "retrieval_url": "https://data.gov.sg/api/action/datastore_search?resource_id=sora&limit=5",
        "definition_url": "https://tablebuilder.singstat.gov.sg/table/TS/M700071",
        "dataset_id": "sora",
        "table_id": "M700071",
        "definition": "Three-month compounded Singapore Overnight Rate Average at month end.",
        "unit": "percent per annum",
        "native_frequency": "monthly",
        "update_frequency": "monthly",
        "series_identifier": "M700071 three-month compounded SORA",
        "schema_orientation": "wide_period_columns",
        "date_field_candidates": ["__period_column__"],
        "value_field_candidates": ["__period_value__"],
        "series_field": "DataSeries",
        "wide_period_format": "singstat_month",
        "exact_series_label": "Compounded Singapore Overnight Rate Average (SORA) - 3 Month",
        "series_type": "rate",
        "point_in_time_notes": "The current endpoint exposes current-vintage history and may not preserve old release vintages.",
        "limitations": ["This is a benchmark financing proxy rather than a mortgage rate."],
    }


def proposal_dict() -> dict:
    return {
        "predictor_id": "financial_predictor_1",
        "scope_summary": "Discover an official public SORA series for the approved private sale-market predictor.",
        "search_queries": [
            {
                "query": "site:mas.gov.sg SORA official data",
                "purpose": "Locate the official definition and public data path.",
            }
        ],
        "candidates": [sora_candidate()],
        "rejected_sources": [],
        "unresolved_questions": [],
    }


def sample_body() -> bytes:
    return json.dumps({
        "success": True,
        "result": {
            "total": 1,
            "records": [{
                "_id": 1,
                "DataSeries": "Compounded Singapore Overnight Rate Average (SORA) - 3 Month",
                "2026Jun": "2.11",
                "2026May": "2.18",
            }],
        },
    }).encode()


class FakeResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, body: bytes, final_url: str):
        self.body = body
        self.final_url = final_url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

    def geturl(self):
        return self.final_url


def passing_probe(candidate: DataSourceCandidate):
    return probe_data_source(
        candidate,
        opener=lambda request, timeout: FakeResponse(sample_body(), request.full_url),
    )


class FakeDiscoveryClient:
    def discover(self, **kwargs):
        proposal = DataDiscoveryProposal.model_validate(proposal_dict())
        return (
            proposal,
            {"id": "discovery-test", "steps": []},
            {"https://data.gov.sg/datasets/sora/view"},
            {"provider": "fake", "model": kwargs["model"]},
        )


class DataDiscoveryTests(unittest.TestCase):
    def test_legacy_discovery_operation_is_discarded_not_approved(self):
        legacy = proposal_dict()
        candidate = legacy["candidates"][0]
        candidate.pop("series_type")
        candidate["proposed_transformation"] = {
            "series_type": "rate",
            "target_frequency": "quarterly",
            "aggregation_method": "mean",
            "change_methods": ["basis_point_change"],
            "incomplete_period_policy": "mark_partial",
            "interpolation_allowed": False,
            "rationale": "Legacy advice must not become an approved operation contract.",
        }
        migrated = load_discovery_proposal(legacy)
        serialized = migrated.model_dump(mode="json")
        self.assertEqual(serialized["candidates"][0]["series_type"], "rate")
        self.assertNotIn("proposed_transformation", serialized["candidates"][0])

    def test_discovery_schema_contains_structure_but_no_operations(self):
        schema = json.dumps(DataDiscoveryProposal.model_json_schema())
        self.assertIn("series_type", schema)
        self.assertNotIn("proposed_transformation", schema)
        self.assertNotIn("aggregation_method", schema)
        self.assertNotIn("change_methods", schema)

    def test_wide_singstat_schema_is_profiled_without_guessing_field_names(self):
        candidate = DataSourceCandidate.model_validate(sora_candidate())
        probe = passing_probe(candidate)
        self.assertEqual(probe.status, "pass")
        self.assertIn("2026Jun", probe.date_field_matches)
        self.assertIn("2026Jun", probe.value_field_matches)
        self.assertIn("DataSeries", probe.fields)
        self.assertEqual(probe.observed_period_start, "2026May")
        self.assertEqual(probe.observed_period_end, "2026Jun")
        self.assertEqual(probe.non_null_observation_count, 2)
        self.assertEqual(probe.missing_observation_count, 0)
        self.assertEqual(probe.coverage_profile_scope, "full_response_series")

    def test_non_official_url_fails_probe(self):
        data = sora_candidate()
        data["retrieval_url"] = "https://example.com/sora.json"
        candidate = DataSourceCandidate.model_validate(data)
        probe = probe_data_source(candidate, opener=lambda *args, **kwargs: None)
        self.assertEqual(probe.status, "fail")
        self.assertTrue(any("allowlist" in item for item in probe.errors))

    def test_schema_hint_mismatch_is_deferred_to_adaptive_mapping(self):
        data = sora_candidate()
        data["series_field"] = "MissingSeriesField"
        candidate = DataSourceCandidate.model_validate(data)
        probe = passing_probe(candidate)
        self.assertEqual(probe.status, "pass")
        self.assertEqual(probe.errors, [])
        self.assertTrue(any("MissingSeriesField" in item for item in probe.warnings))

    def test_unique_spacing_difference_is_resolved_to_actual_field(self):
        data = sora_candidate()
        data["series_field"] = "Data Series"
        candidate = DataSourceCandidate.model_validate(data)
        probe = passing_probe(candidate)
        self.assertEqual(probe.status, "pass")
        self.assertEqual(probe.series_field_match, "DataSeries")
        self.assertTrue(any("Data Series" in item for item in probe.field_adjustments))

    def test_validation_builds_unapproved_draft_only_after_probe(self):
        proposal = DataDiscoveryProposal.model_validate(proposal_dict())
        predictor = ResearchProposal.model_validate(valid_proposal_dict()).candidates[1]
        probe = passing_probe(proposal.candidates[0])
        validation = validate_discovery(
            proposal,
            predictor,
            [probe],
            searched_urls={"https://data.gov.sg/datasets/sora/view"},
        )
        drafts = build_draft_entries(proposal, validation, [probe])
        self.assertEqual(validation.automated_validation_status, "pass")
        self.assertEqual(validation.human_review_status, "pending")
        self.assertEqual(drafts[0].draft_status, "unapproved")
        self.assertEqual(drafts[0].proposed_date_field, "__period_column__")
        self.assertEqual(drafts[0].series_type.value, "rate")

    def test_node_requires_predictor_to_be_human_approved(self):
        node = make_data_discovery_node(lambda: FakeDiscoveryClient(), passing_probe)
        result = node({
            "approved_scope": approved_scope(),
            "approved_predictors": [],
            "target_predictor_id": "financial_predictor_1",
        })
        self.assertEqual(result["discovery_metadata"]["execution_status"], "fail")
        self.assertTrue(any("human-approved" in item for item in result["discovery_errors"]))

    def test_node_persists_probe_and_draft_without_touching_production_catalog(self):
        predictor = ResearchProposal.model_validate(valid_proposal_dict()).candidates[1]
        node = make_data_discovery_node(lambda: FakeDiscoveryClient(), passing_probe)
        with tempfile.TemporaryDirectory() as temporary:
            result = node({
                "approved_scope": ApprovedResearchScope.model_validate(approved_scope()).model_dump(mode="json"),
                "approved_predictors": [predictor.model_dump(mode="json")],
                "target_predictor_id": predictor.predictor_id,
                "discovery_artifact_dir": temporary,
            })
            self.assertEqual(result["discovery_metadata"]["execution_status"], "success")
            self.assertEqual(result["discovery_validation"]["automated_validation_status"], "pass")
            self.assertEqual(len(result["draft_catalog_entries"]), 1)
            self.assertTrue((Path(temporary) / "source_probes.json").is_file())
            draft_file = json.loads(
                (Path(temporary) / "draft_catalog_entries.json").read_text()
            )
            self.assertEqual(draft_file["catalog_status"], "draft_unapproved")

    def test_node_researches_again_after_deterministic_probe_failure(self):
        bad_data = sora_candidate()
        bad_data.update({
            "candidate_id": "mas_display_page",
            "source_type": "html_report",
            "source_page_url": "https://eservices.mas.gov.sg/statistics/dir/DomesticInterestRates.aspx",
            "retrieval_url": "https://eservices.mas.gov.sg/statistics/dir/DomesticInterestRates.aspx",
            "schema_orientation": "long_records",
            "date_field_candidates": ["Date"],
            "value_field_candidates": ["Value"],
            "series_field": None,
            "wide_period_format": None,
        })
        bad_proposal = proposal_dict()
        bad_proposal["candidates"] = [bad_data]

        class RetryClient:
            def __init__(self):
                self.inputs = []

            def discover(self, **kwargs):
                self.inputs.append(kwargs["input_text"])
                data = bad_proposal if len(self.inputs) == 1 else proposal_dict()
                return (
                    DataDiscoveryProposal.model_validate(data),
                    {"attempt": len(self.inputs)},
                    {data["candidates"][0]["source_page_url"]},
                    {"provider": "fake", "model": kwargs["model"]},
                )

        client = RetryClient()

        def conditional_probe(candidate):
            if candidate.candidate_id == "mas_display_page":
                return SourceProbeResult(
                    candidate_id=candidate.candidate_id,
                    status="fail",
                    requested_url=candidate.retrieval_url,
                    final_url=candidate.retrieval_url,
                    http_status=200,
                    content_type="text/html",
                    bytes_sampled=100,
                    detected_format="unsupported",
                    fields=[],
                    sample_record_count=0,
                    total_record_count=None,
                    date_field_matches=[],
                    value_field_matches=[],
                    series_field_match=None,
                    field_adjustments=[],
                    errors=["HTML display page is not a machine-readable endpoint."],
                    warnings=[],
                )
            return passing_probe(candidate)

        predictor = ResearchProposal.model_validate(valid_proposal_dict()).candidates[1]
        result = make_data_discovery_node(lambda: client, conditional_probe)({
            "approved_scope": approved_scope(),
            "approved_predictors": [predictor.model_dump(mode="json")],
            "target_predictor_id": predictor.predictor_id,
            "max_discovery_attempts": 2,
        })
        self.assertEqual(len(client.inputs), 2)
        self.assertIn("PREVIOUS ATTEMPT FAILED", client.inputs[1])
        self.assertEqual(
            result["discovery_validation"]["automated_validation_status"], "pass"
        )
        self.assertEqual(result["discovery_metadata"]["discovery_attempt_count"], 2)


if __name__ == "__main__":
    unittest.main()
