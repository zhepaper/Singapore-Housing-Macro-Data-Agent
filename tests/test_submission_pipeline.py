from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SubmissionPipelineTests(unittest.TestCase):
    def test_offline_submission_pipeline_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "submission"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_submission_pipeline.py",
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            summary = json.loads((output / "workflow_summary.json").read_text())
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["stage3_status"], "success")
            self.assertEqual(summary["stage4_status"], "success")
            self.assertTrue((output / "stage4" / "final_report.md").exists())
            verification = json.loads(
                (output / "stage4" / "verification_report.json").read_text()
            )
            self.assertEqual(verification["status"], "pass")


if __name__ == "__main__":
    unittest.main()
