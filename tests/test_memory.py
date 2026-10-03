import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from housing_agent.memory.compiler import compile_memory, memory_compiler_node
from housing_agent.memory.models import DecisionEvent
from housing_agent.memory.store import DecisionLogStore


SEED_PATH = Path("config/project_memory.seed.jsonl")


class MemoryTests(unittest.TestCase):
    def test_seed_compiles_to_stable_confirmed_memory(self):
        events = DecisionLogStore(SEED_PATH).load()
        first, first_manifest = compile_memory(events)
        second, second_manifest = compile_memory(events)
        self.assertEqual(first.memory_version, 7)
        self.assertEqual(len(first.approved_predictors), 7)
        self.assertTrue(first.data_preferences.preserve_native_frequency)
        self.assertFalse(first.data_preferences.annual_interpolation_allowed)
        self.assertEqual(len(first.pending_questions), 1)
        self.assertEqual(
            first_manifest.snapshot_sha256, second_manifest.snapshot_sha256
        )

    def test_compiler_persists_snapshot_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = memory_compiler_node({
                "memory_decision_log_path": str(SEED_PATH),
                "memory_artifact_dir": temporary,
            })
            version = result["memory_snapshot"]["memory_version"]
            self.assertTrue((Path(temporary) / f"memory_v{version}.json").is_file())
            manifest = json.loads(
                (Path(temporary) / "memory_manifest.json").read_text()
            )
            self.assertEqual(len(manifest["snapshot_sha256"]), 64)

    def test_secret_like_fields_are_rejected(self):
        event = {
            "event_id": "bad_secret",
            "project_id": "test_project",
            "sequence": 1,
            "recorded_at": "2026-10-02T00:00:00Z",
            "actor": "human",
            "status": "confirmed",
            "decision_type": "data_preferences",
            "payload": {"api_key": "must-not-be-stored"},
            "rationale": "Test secret rejection.",
            "evidence": [],
            "supersedes": None,
        }
        with self.assertRaises(ValidationError):
            DecisionEvent.model_validate(event)

    def test_store_is_append_only_and_requires_contiguous_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = DecisionLogStore(Path(temporary) / "events.jsonl")
            base = {
                "project_id": "test_project",
                "recorded_at": datetime.now(timezone.utc),
                "actor": "human",
                "status": "confirmed",
                "decision_type": "research_preferences",
                "payload": {"choice": "x"},
                "rationale": "Test event sequence.",
                "evidence": [],
                "supersedes": None,
            }
            store.append(DecisionEvent(event_id="event_1", sequence=1, **base))
            with self.assertRaises(ValueError):
                store.append(DecisionEvent(event_id="event_3", sequence=3, **base))
            self.assertEqual(len(store.load()), 1)

    def test_pending_preference_does_not_replace_confirmed_preference(self):
        events = DecisionLogStore(SEED_PATH).load()
        next_event = DecisionEvent(
            event_id="pending_data_change",
            project_id=events[0].project_id,
            sequence=8,
            recorded_at=datetime(2026, 10, 2, 17, tzinfo=timezone.utc),
            actor="llm_proposal",
            status="pending",
            decision_type="data_preferences",
            payload={"preserve_native_frequency": False},
            rationale="Unconfirmed model suggestion.",
            evidence=[],
        )
        snapshot, _ = compile_memory([*events, next_event])
        self.assertTrue(snapshot.data_preferences.preserve_native_frequency)


if __name__ == "__main__":
    unittest.main()
