from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from sts_ai_assistant.parsing.models import GameSnapshot


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class RecommendationResult:
    screen_type: str
    suggested_action: str
    reasoning: str
    primary_target: str | None = None
    build_direction: str | None = None
    alternatives: list[str] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_type": self.screen_type,
            "suggested_action": self.suggested_action,
            "primary_target": self.primary_target,
            "reasoning": self.reasoning,
            "build_direction": self.build_direction,
            "alternatives": self.alternatives,
            "raw_response": self.raw_response,
        }


@dataclass(slots=True)
class AssistantReply:
    mode: str
    conclusion: str
    reasons: list[str]
    alternatives: list[str]
    build_direction: str | None = None
    source: str = "auto"
    created_at: str = field(default_factory=now_iso)
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "conclusion": self.conclusion,
            "reasons": list(self.reasons),
            "alternatives": list(self.alternatives),
            "build_direction": self.build_direction,
            "source": self.source,
            "created_at": self.created_at,
            "raw_response": self.raw_response,
        }


@dataclass(slots=True)
class ChatTurn:
    question: str
    reply: AssistantReply
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "reply": self.reply.to_dict(),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class AssistantSession:
    session_id: str
    latest_analysis: AssistantReply | None = None
    chat_history: list[ChatTurn] = field(default_factory=list)
    started_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def set_latest_analysis(self, reply: AssistantReply) -> None:
        self.latest_analysis = reply
        self.updated_at = now_iso()

    def append_chat_turn(self, question: str, reply: AssistantReply, max_turns: int = 8) -> None:
        self.chat_history.append(ChatTurn(question=question, reply=reply))
        if len(self.chat_history) > max_turns:
            self.chat_history = self.chat_history[-max_turns:]
        self.updated_at = now_iso()

    def to_dict(self, memory_enabled: bool = True) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "latest_analysis": self.latest_analysis.to_dict() if self.latest_analysis else None,
            "chat_history": [turn.to_dict() for turn in self.chat_history],
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "memory_enabled": memory_enabled,
        }


class LLMClient(Protocol):
    def recommend(self, snapshot: GameSnapshot) -> RecommendationResult:
        """Return a structured recommendation for the current screen."""

    def analyze(
        self,
        snapshot: GameSnapshot,
        source: str,
        focus: str | None = None,
    ) -> AssistantReply:
        """Return a Chinese assistant analysis for the current game state."""

    def chat(
        self,
        snapshot: GameSnapshot,
        source: str,
        message: str,
        history: list[ChatTurn] | None = None,
    ) -> AssistantReply:
        """Answer a question using the latest game state and recent memory."""
