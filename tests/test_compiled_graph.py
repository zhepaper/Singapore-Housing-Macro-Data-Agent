import json
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from housing_agent.workflow import (
    build_graph,
    checkpoint_retrieved_node,
    discover_snapshots_node,
    initialize_run_node,
    load_catalog_node,
)


class CompiledGraphTests(unittest.TestCase):
    def test_snapshot_graph_persists_complete_run(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(repository / "config", root / "config")
            shutil.copytree(repository / "data", root / "data")
            result = build_graph().invoke({
                "reporting_as_of_date": "2026-10-01",
                "project_root": str(root),
                "execution_mode": "snapshots",
                "request_interval_seconds": 0.0,
            })
            self.assertEqual(result["run_status"], "complete")
            run_root = Path(result["run_paths"]["root"])
            self.assertTrue((run_root / "normalized/observations.jsonl").is_file())
            self.assertTrue((run_root / "metrics/derived_observations.jsonl").is_file())
            self.assertTrue((run_root / "metrics/evidence.json").is_file())
            self.assertTrue((run_root / "report/report.md").is_file())
            for stage in ("retrieved", "normalized", "transformed", "validated"):
                self.assertTrue((run_root / f"checkpoints/{stage}.json").is_file())

            manifest_schema = json.loads((repository / "schemas/run-manifest.schema.json").read_text())
            observation_schema = json.loads((repository / "schemas/observation.schema.json").read_text())
            evidence_schema = json.loads((repository / "schemas/evidence.schema.json").read_text())
            manifest = json.loads((run_root / "run_manifest.json").read_text())
            Draft202012Validator(manifest_schema, format_checker=FormatChecker()).validate(manifest)
            self.assertTrue(all(not Path(path).is_absolute() for path in manifest["artifacts"].values()))
            self.assertEqual(len(list((run_root / "raw").glob("*"))), 8)
            observation_validator = Draft202012Validator(
                observation_schema, format_checker=FormatChecker()
            )
            with (run_root / "normalized/observations.jsonl").open() as handle:
                for line in handle:
                    item = json.loads(line)
                    observation_validator.validate(item)
                    self.assertEqual(item["run_id"], result["run_id"])
                    self.assertTrue(item["provenance_id"].startswith(result["run_id"] + ":"))
            evidence = json.loads((run_root / "metrics/evidence.json").read_text())
            evidence_validator = Draft202012Validator(
                evidence_schema, format_checker=FormatChecker()
            )
            for item in evidence.values():
                evidence_validator.validate(item)
                self.assertFalse(Path(item["raw_snapshot_path"]).is_absolute())

    def test_graph_resumes_after_retrieval_checkpoint(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(repository / "config", root / "config")
            shutil.copytree(repository / "data", root / "data")
            state = {
                "reporting_as_of_date": "2026-10-01",
                "project_root": str(root),
                "execution_mode": "snapshots",
            }
            for node in (load_catalog_node, initialize_run_node, discover_snapshots_node):
                state.update(node(state))
            checkpoint_retrieved_node(state)

            resumed = build_graph(resume_from="normalize").invoke(state)
            self.assertEqual(resumed["run_status"], "complete")
            self.assertTrue(Path(resumed["run_paths"]["report"]).joinpath("report.md").is_file())


if __name__ == "__main__":
    unittest.main()
