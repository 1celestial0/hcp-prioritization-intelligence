"""Append-only JSONL audit trail.

Records are added with open(..., "a"). This module never truncates or rewrites
earlier lines. A retrieval failure is logged as its own fallback event.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event_type: str, **payload: object) -> dict:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **payload,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, sort_keys=True, default=str) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
        return event

    def read_events(self) -> list[dict]:
        if not self.path.exists():
            return []
        events: list[dict] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    events.append(json.loads(stripped))
        return events

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open(encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
