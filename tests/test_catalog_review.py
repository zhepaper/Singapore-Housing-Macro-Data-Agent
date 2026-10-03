import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from housing_agent.onboarding.catalog_review import catalog_review_node
from housing_agent.onboarding.discovery import (
    DataDiscoveryProposal,
    build_draft_entries,
    validate_discovery,
)
from housing_agent.research.models import ResearchProposal
from tests.test_data_discovery import passing_probe, proposal_dict
from tests.test_research_search_node import valid_proposal_dict


def draft_entries() -> list[dict]:
    proposal = DataDiscoveryProposal.model_validate(proposal_dict())
    predictor = ResearchProposal.model_validate(valid_proposal_dict()).candidates[1]
    probe = passing_probe(proposal.candidates[0])
    validation = validate_discovery(proposal, predictor, [probe])
    return [
        item.model_dump(mode="json")
        for item in build_draft_entries(proposal, validation, [probe])
    ]


def submission(entries: list[dict], decision: str = "approve") -> dict:
    return {
        "catalog_version": "discovery-1",
        "reviewer": "human_reviewer",
        "candidate_reviews": [
            {
                "candidate_id": item["candidate_id"],
                "decision": decision,
                "review_notes": [] if decision == "approve" else ["Needs correction."],
            }
            for item in entries
        ],
        "overall_notes": ["Checked official source, schema, unit, and definition."],
    }


class CatalogReviewTests(unittest.TestCase):
    def test_approved_fragment_is_separate_and_versioned(self):
        entries = draft_entries()
        with tempfile.TemporaryDirectory() as temporary:
            result = catalog_review_node({
                "draft_catalog_entries": entries,
                "catalog_review_submission": submission(entries),
                "catalog_review_artifact_dir": temporary,
            })
            self.assertEqual(result["catalog_review_result"]["review_status"], "approved")
            self.assertEqual(len(result["approved_catalog_entries"]), 1)
            fragment = Path(temporary) / "approved_catalog_fragment.json"
            self.assertTrue(fragment.is_file())
            saved = json.loads(fragment.read_text())
            self.assertEqual(saved["catalog_status"], "human_approved_fragment")
            self.assertEqual(saved["catalog_version"], "discovery-1")

    def test_catalog_approval_contains_no_analytical_operation_contract(self):
        entries = draft_entries()
        result = catalog_review_node({
            "draft_catalog_entries": entries,
            "catalog_review_submission": submission(entries),
        })
        self.assertEqual(result["catalog_review_result"]["review_status"], "approved")
        entry = result["approved_catalog_entries"][0]["entry"]
        self.assertEqual(entry["series_type"], "rate")
        self.assertNotIn("transformation_contract", entry)

    def test_failed_probe_cannot_be_approved(self):
        entries = draft_entries()
        entries[0]["probe"]["status"] = "fail"
        entries[0]["probe"]["errors"] = ["schema drift"]
        result = catalog_review_node({
            "draft_catalog_entries": entries,
            "catalog_review_submission": submission(entries),
        })
        self.assertEqual(result["catalog_review_result"]["review_status"], "invalid")

    def test_request_revision_does_not_emit_approved_entry(self):
        entries = draft_entries()
        result = catalog_review_node({
            "draft_catalog_entries": entries,
            "catalog_review_submission": submission(entries, "request_revision"),
        })
        self.assertEqual(result["catalog_review_result"]["review_status"], "needs_revision")
        self.assertEqual(result["approved_catalog_entries"], [])

    def test_only_one_primary_source_can_be_approved_per_predictor(self):
        entries = draft_entries()
        second = deepcopy(entries[0])
        second["candidate_id"] = "sora_second_source"
        second["source_id"] = "sora_second_source"
        second["probe"]["candidate_id"] = "sora_second_source"
        entries.append(second)
        result = catalog_review_node({
            "draft_catalog_entries": entries,
            "catalog_review_submission": submission(entries),
        })
        self.assertEqual(result["catalog_review_result"]["review_status"], "invalid")
        self.assertTrue(any(
            "one approved primary source" in item
            for item in result["catalog_review_result"]["errors"]
        ))


if __name__ == "__main__":
    unittest.main()
