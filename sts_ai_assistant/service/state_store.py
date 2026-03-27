from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any

from sts_ai_assistant.llm.base import AssistantSession, RecommendationResult
from sts_ai_assistant.parsing.models import GameSnapshot


class LatestStateStore:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._latest_snapshot: GameSnapshot | None = None
        self._payload: dict[str, Any] = {
            "updated_at": None,
            "latest_state": None,
            "latest_recommendation": None,
            "assistant": self._serialize_assistant(None),
        }

    def update_snapshot(self, snapshot: GameSnapshot) -> None:
        with self._lock:
            self._latest_snapshot = snapshot
            self._payload["updated_at"] = self._now_iso()
            self._payload["latest_state"] = snapshot.to_dict()
            self._flush()

    def update_recommendation(
        self,
        snapshot: GameSnapshot,
        recommendation: RecommendationResult,
    ) -> None:
        with self._lock:
            self._latest_snapshot = snapshot
            self._payload["updated_at"] = self._now_iso()
            self._payload["latest_state"] = snapshot.to_dict()
            self._payload["latest_recommendation"] = recommendation.to_dict()
            self._flush()

    def update_assistant_session(self, session: AssistantSession | None) -> None:
        with self._lock:
            self._payload["updated_at"] = self._now_iso()
            self._payload["assistant"] = self._serialize_assistant(session)
            self._flush()

    def get_latest_snapshot(self) -> GameSnapshot | None:
        with self._lock:
            return self._latest_snapshot

    def get_payload(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._payload, ensure_ascii=False))

    def _serialize_assistant(self, session: AssistantSession | None) -> dict[str, Any]:
        if session is None:
            return {
                "session_id": None,
                "latest_analysis": None,
                "chat_history": [],
                "started_at": None,
                "updated_at": None,
                "memory_enabled": True,
            }
        return session.to_dict(memory_enabled=True)

    def _flush(self) -> None:
        with self.output_path.open("w", encoding="utf-8") as handle:
            json.dump(self._payload, handle, ensure_ascii=False, indent=2)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
