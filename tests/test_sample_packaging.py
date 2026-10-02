import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SamplePackagingTests(unittest.TestCase):
    def test_script_rejects_non_complete_run(self):
        repository = Path(__file__).resolve().parents[1]
        runs_directory = repository / "runs"
        runs_directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runs_directory) as temporary:
            run_root = Path(temporary)
            (run_root / "run_manifest.json").write_text(json.dumps({"status": "failed"}))
            destination = run_root / "sample"
            result = subprocess.run(
                [sys.executable,
                 str(repository / "scripts/package_sample_run.py"),
                 "--run-id", run_root.name, "--destination", str(destination)],
                cwd=repository, text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
