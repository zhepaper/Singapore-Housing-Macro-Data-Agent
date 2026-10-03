import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from housing_agent.onboarding.models import PredictorReviewSubmission
from housing_agent.onboarding.review import review_predictors_node
from housing_agent.research.models import ApprovedResearchScope, ResearchProposal
from housing_agent.research.validation import validate_research_proposal
from housing_agent.memory.store import DecisionLogStore
from tests.test_research_search_node import approved_scope, valid_proposal_dict


def review_submission(proposal: dict, *, decision: str = "approve") -> dict:
    return {
        "review_version": 1,
        "reviewer": "human_reviewer",
        "candidate_reviews": [
            {
                "predictor_id": item["predictor_id"],
                "decision": decision,
                "review_notes": [] if decision == "approve" else ["Not selected."],
                "selection_rationale": (
                    ["Selected for its supported and distinct market mechanism."]
                    if decision == "approve"
                    else []
                ),
            }
            for item in proposal["candidates"]
        ],
        "overall_notes": ["Reviewed against the approved private-market scope."],
    }


def review_state(proposal_data: dict | None = None) -> dict:
    proposal_data = proposal_data or valid_proposal_dict()
    proposal = ResearchProposal.model_validate(proposal_data)
    scope = ApprovedResearchScope.model_validate(approved_scope())
    validation = validate_research_proposal(proposal, scope)
    return {
        "approved_scope": scope.model_dump(mode="json"),
        "research_proposal": proposal.model_dump(mode="json"),
        "research_validation": validation.model_dump(mode="json"),
        "predictor_review_submission": review_submission(proposal_data),
    }


class PredictorReviewTests(unittest.TestCase):
    def test_approval_rationale_is_appended_to_memory_idempotently(self):
        state = review_state()
        with tempfile.TemporaryDirectory() as temporary:
            decision_log = Path(temporary) / "memory.jsonl"
            decision_log.write_text(
                Path("config/project_memory.seed.jsonl").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            state["memory_decision_log_path"] = str(decision_log)
            first = review_predictors_node(state)
            second = review_predictors_node(state)
            events = DecisionLogStore(decision_log).load()
            self.assertEqual(len(events), 8)
            self.assertEqual(
                first["predictor_approval_memory_event"]["event_id"],
                second["predictor_approval_memory_event"]["event_id"],
            )
            self.assertEqual(events[-1].decision_type, "predictor_approval")
            self.assertTrue(
                events[-1].payload["predictors"][0]["selection_rationale"]
            )

    def test_complete_approval_is_versioned_and_persisted(self):
        state = review_state()
        with tempfile.TemporaryDirectory() as temporary:
            state["predictor_review_artifact_dir"] = temporary
            result = review_predictors_node(state)
            review = result["predictor_review_result"]
            self.assertEqual(review["review_status"], "approved")
            self.assertEqual(len(result["approved_predictors"]), 4)
            artifact = Path(temporary) / "approved_predictors.json"
            self.assertTrue(artifact.is_file())
            saved = json.loads(artifact.read_text())
            self.assertEqual(saved["review_version"], 1)
            self.assertEqual(len(saved["predictors"]), 4)

    def test_missing_candidate_decision_is_invalid(self):
        state = review_state()
        state["predictor_review_submission"]["candidate_reviews"].pop()
        result = review_predictors_node(state)
        self.assertEqual(
            result["predictor_review_result"]["review_status"], "invalid"
        )
        self.assertTrue(any(
            "missing" in error.lower()
            for error in result["predictor_review_result"]["errors"]
        ))

    def test_revision_request_prevents_approval(self):
        state = review_state()
        review = state["predictor_review_submission"]["candidate_reviews"][0]
        review["decision"] = "request_revision"
        review["review_notes"] = ["Clarify the rental mechanism."]
        result = review_predictors_node(state)
        self.assertEqual(
            result["predictor_review_result"]["review_status"], "needs_revision"
        )

    def test_approval_must_retain_sale_and_rent_coverage(self):
        proposal = valid_proposal_dict()
        for item in proposal["candidates"]:
            item["market_role"] = "sale_focused"
            item["mechanisms"] = [item["mechanisms"][0]]
        state = review_state(proposal)
        result = review_predictors_node(state)
        self.assertEqual(
            result["predictor_review_result"]["review_status"], "invalid"
        )
        self.assertTrue(any(
            "private_residential/rent" in error
            for error in result["predictor_review_result"]["errors"]
        ))

    def test_reject_requires_a_reason(self):
        proposal = valid_proposal_dict()
        submission = review_submission(proposal, decision="reject")
        submission["candidate_reviews"][0]["review_notes"] = []
        with self.assertRaises(ValueError):
            PredictorReviewSubmission.model_validate(submission)

    def test_hard_gate_failure_cannot_be_human_approved(self):
        state = review_state()
        validation = deepcopy(state["research_validation"])
        validation["candidate_scores"][0]["hard_gate_status"] = "fail"
        validation["candidate_scores"][0]["hard_gate_failures"] = ["bad evidence"]
        state["research_validation"] = validation
        result = review_predictors_node(state)
        self.assertEqual(
            result["predictor_review_result"]["review_status"], "invalid"
        )


if __name__ == "__main__":
    unittest.main()
