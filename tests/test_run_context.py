import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from housing_agent.run_context import (
    finalize_manifest,
    generate_run_id,
    initialize_run,
    load_latest_checkpoint,
    load_run,
    save_checkpoint,
)


class RunContextTests(unittest.TestCase):
    def test_run_id_is_utc_and_sortable(self):
        value = generate_run_id(datetime(2026, 10, 1, 12, 30, 45, 123456, tzinfo=timezone.utc))
        self.assertEqual(value, "20261001T123045123456Z")

    def test_initialize_checkpoint_resume_and_finalize(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_id, paths, manifest = initialize_run(
                project_root=root,
                reporting_as_of_date="2026-10-01",
                catalog_version="1",
                prompt_version="deterministic-v1",
                run_id="test-run",
            )
            self.assertEqual(manifest["status"], "running")
            self.assertTrue(Path(paths.raw).is_dir())
            checkpoint = save_checkpoint(paths, "normalized", {"run_id": run_id, "count": 3})
            self.assertEqual(json.loads(Path(checkpoint).read_text())["count"], 3)
            stage, checkpoint_state = load_latest_checkpoint(paths)
            self.assertEqual(stage, "normalized")
            self.assertEqual(checkpoint_state["count"], 3)

            loaded_paths, loaded_manifest = load_run(root, run_id)
            self.assertEqual(loaded_paths, paths)
            self.assertEqual(loaded_manifest["run_id"], run_id)

            final = finalize_manifest(
                paths,
                status="complete",
                sources=[],
                validation_errors=[],
                counts={"observations": 3},
            )
            self.assertEqual(final["status"], "complete")
            self.assertIsNotNone(final["completed_at"])

    def test_run_directory_is_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_run(
                project_root=root,
                reporting_as_of_date="2026-10-01",
                catalog_version="1",
                prompt_version="v1",
                run_id="duplicate",
            )
            with self.assertRaises(FileExistsError):
                initialize_run(
                    project_root=root,
                    reporting_as_of_date="2026-10-01",
                    catalog_version="1",
                    prompt_version="v1",
                    run_id="duplicate",
                )


if __name__ == "__main__":
    unittest.main()
