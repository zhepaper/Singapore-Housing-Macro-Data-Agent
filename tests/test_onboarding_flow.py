import hashlib
import unittest
from pathlib import Path

from housing_agent.onboarding.catalog_review import catalog_review_node
from housing_agent.onboarding.discovery import make_data_discovery_node
from housing_agent.onboarding.review import review_predictors_node
from housing_agent.research.models import ApprovedResearchScope, ResearchProposal
from housing_agent.research.validation import validate_research_proposal
from tests.test_catalog_review import submission as catalog_submission
from tests.test_data_discovery import FakeDiscoveryClient, passing_probe
from tests.test_predictor_review import review_submission
from tests.test_research_search_node import approved_scope, valid_proposal_dict


class OnboardingFlowTests(unittest.TestCase):
    def test_review_discovery_and_catalog_freeze_do_not_mutate_production(self):
        production = Path("config/data_catalog.yaml")
        before = hashlib.sha256(production.read_bytes()).hexdigest()
        scope = ApprovedResearchScope.model_validate(approved_scope())
        proposal = ResearchProposal.model_validate(valid_proposal_dict())
        validation = validate_research_proposal(proposal, scope)

        predictor_review = review_predictors_node({
            "approved_scope": scope.model_dump(mode="json"),
            "research_proposal": proposal.model_dump(mode="json"),
            "research_validation": validation.model_dump(mode="json"),
            "predictor_review_submission": review_submission(valid_proposal_dict()),
        })
        self.assertEqual(
            predictor_review["predictor_review_result"]["review_status"],
            "approved",
        )

        discovery = make_data_discovery_node(
            lambda: FakeDiscoveryClient(), passing_probe
        )({
            "approved_scope": scope.model_dump(mode="json"),
            "approved_predictors": predictor_review["approved_predictors"],
            "target_predictor_id": "financial_predictor_1",
        })
        self.assertEqual(
            discovery["discovery_validation"]["automated_validation_status"],
            "pass",
        )

        catalog_review = catalog_review_node({
            "draft_catalog_entries": discovery["draft_catalog_entries"],
            "catalog_review_submission": catalog_submission(
                discovery["draft_catalog_entries"]
            ),
        })
        self.assertEqual(
            catalog_review["catalog_review_result"]["review_status"],
            "approved",
        )
        self.assertEqual(len(catalog_review["approved_catalog_entries"]), 1)
        after = hashlib.sha256(production.read_bytes()).hexdigest()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
