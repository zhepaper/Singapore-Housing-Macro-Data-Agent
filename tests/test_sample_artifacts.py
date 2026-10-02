import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


class SampleArtifactTests(unittest.TestCase):
    def test_sample_run_is_complete_portable_and_checksum_valid(self):
        repository = Path(__file__).resolve().parents[1]
        sample = repository / "sample_run"
        manifest = json.loads((sample / "run_manifest.json").read_text())
        schema = json.loads((repository / "schemas/run-manifest.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["counts"]["observations"], 2012)
        self.assertEqual(manifest["counts"]["derived_observations"], 1846)
        self.assertEqual(manifest["counts"]["evidence_series"], 20)
        self.assertTrue(all(not Path(path).is_absolute() for path in manifest["artifacts"].values()))
        for artifact in manifest["artifacts"].values():
            self.assertTrue((repository / artifact).exists(), artifact)
        for source in manifest["sources"]:
            path = repository / source["raw_snapshot_path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source["raw_file_sha256"])
        verification = json.loads((sample / "report/verification.json").read_text())
        validation = json.loads((sample / "validation_report.json").read_text())
        evidence = json.loads((sample / "metrics/evidence.json").read_text())
        evidence_schema = json.loads((repository / "schemas/evidence.schema.json").read_text())
        evidence_validator = Draft202012Validator(
            evidence_schema, format_checker=FormatChecker()
        )
        for item in evidence.values():
            evidence_validator.validate(item)
        self.assertEqual(verification["status"], "pass")
        self.assertEqual(validation["status"], "pass")


if __name__ == "__main__":
    unittest.main()
