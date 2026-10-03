from __future__ import annotations

import json
from pathlib import Path

from housing_agent.memory.models import DecisionEvent


class DecisionLogStore:
    """Append-only JSONL storage for human-governed project decisions."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[DecisionEvent]:
        if not self.path.exists():
            return []
        events = [
            DecisionEvent.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        ids: set[str] = set()
        previous_sequence = 0
        project_id: str | None = None
        for event in events:
            if event.event_id in ids:
                raise ValueError(f"duplicate memory event ID: {event.event_id}")
            if event.sequence != previous_sequence + 1:
                raise ValueError("memory event sequences must be contiguous and ordered")
            if project_id is not None and event.project_id != project_id:
                raise ValueError("a decision log cannot mix project IDs")
            if event.supersedes and event.supersedes not in ids:
                raise ValueError(
                    f"memory event {event.event_id} supersedes an unknown or later event"
                )
            ids.add(event.event_id)
            previous_sequence = event.sequence
            project_id = event.project_id
        return events

    def append(self, event: DecisionEvent) -> None:
        events = self.load()
        if events:
            if event.project_id != events[0].project_id:
                raise ValueError("new event project ID does not match the decision log")
            if event.sequence != events[-1].sequence + 1:
                raise ValueError("new event sequence must follow the current log")
            if event.event_id in {item.event_id for item in events}:
                raise ValueError("new event ID already exists")
            if event.supersedes and event.supersedes not in {
                item.event_id for item in events
            }:
                raise ValueError("supersedes must reference an existing event")
        elif event.sequence != 1:
            raise ValueError("the first event sequence must be 1")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
