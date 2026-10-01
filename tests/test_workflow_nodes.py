import unittest
from pathlib import Path

from housing_agent.workflow import (
    build_evidence_node,
    discover_snapshots_node,
    load_catalog_node,
    normalize_node,
    transform_node,
    validate_node,
)


class WorkflowNodeTests(unittest.TestCase):
    def test_real_snapshots_reach_validated_state(self):
        root = Path(__file__).resolve().parents[1]
        state = {"project_root": str(root), "reporting_as_of_date": "2026-10-01"}
        state.update(load_catalog_node(state))
        state.update(discover_snapshots_node(state))
        state.update(normalize_node(state))
        state.update(transform_node(state))
        state.update(validate_node(state))
        self.assertEqual(state["validation_errors"], [])
        self.assertEqual(state["run_status"], "validated")
        state.update(build_evidence_node(state))
        self.assertIn("private_non_landed_vacancy_rate__rate", state["evidence"])
        self.assertNotIn(
            "private_non_landed_vacancy_rate__available_non_landed_properties",
            state["evidence"],
        )

    def test_mom_report_after_cutoff_is_rejected(self):
        root = Path(__file__).resolve().parents[1]
        state = {"project_root": str(root), "reporting_as_of_date": "2026-09-01"}
        state.update(load_catalog_node(state))
        state.update(discover_snapshots_node(state))
        state.update(normalize_node(state))
        self.assertTrue(any("released after the as-of date" in error for error in state["validation_errors"]))


if __name__ == "__main__":
    unittest.main()
