from __future__ import annotations

import logging
from threading import Lock
from uuid import uuid4

from sts_ai_assistant.llm.base import AssistantReply, AssistantSession, LLMClient, RecommendationResult
from sts_ai_assistant.parsing.models import GameSnapshot
from sts_ai_assistant.service.state_store import LatestStateStore


class AssistantService:
    def __init__(
        self,
        llm_client: LLMClient,
        state_store: LatestStateStore,
        logger: logging.Logger | None = None,
        max_chat_turns: int = 8,
    ) -> None:
        self.llm_client = llm_client
        self.state_store = state_store
        self.logger = logger or logging.getLogger(__name__)
        self.max_chat_turns = max_chat_turns
        self._lock = Lock()
        self._session: AssistantSession | None = None
        self._last_snapshot: GameSnapshot | None = None

    def on_snapshot(self, snapshot: GameSnapshot) -> None:
        with self._lock:
            if not snapshot.in_game:
                self._session = None
                self._last_snapshot = snapshot
                self.state_store.update_assistant_session(None)
                return

            if self._should_start_new_session(snapshot):
                self._session = AssistantSession(session_id=uuid4().hex)
                self.logger.info(
                    "Assistant session started | session=%s floor=%s class=%s",
                    self._session.session_id,
                    snapshot.floor,
                    snapshot.character_class,
                )

            self._last_snapshot = snapshot
            self.state_store.update_assistant_session(self._session)

    def record_auto_recommendation(
        self,
        snapshot: GameSnapshot,
        recommendation: RecommendationResult,
    ) -> AssistantReply:
        reply = self._reply_from_recommendation(recommendation)
        with self._lock:
            self._ensure_session(snapshot)
            if self._session is not None:
                self._session.set_latest_analysis(reply)
                self.state_store.update_assistant_session(self._session)
        return reply

    def analyze(self, source: str, focus: str | None = None) -> AssistantReply:
        snapshot = self.state_store.get_latest_snapshot()
        if snapshot is None or not snapshot.in_game:
            return self._no_state_reply(mode="analysis", source=source)

        with self._lock:
            self._ensure_session(snapshot)

        reply = self.llm_client.analyze(snapshot, source=source, focus=focus)
        with self._lock:
            if self._session is not None:
                self._session.set_latest_analysis(reply)
                self.state_store.update_assistant_session(self._session)
        return reply

    def chat(self, source: str, message: str) -> AssistantReply:
        snapshot = self.state_store.get_latest_snapshot()
        if snapshot is None or not snapshot.in_game:
            return self._no_state_reply(mode="chat", source=source, message=message)

        with self._lock:
            self._ensure_session(snapshot)
            history = list(self._session.chat_history if self._session is not None else [])

        reply = self.llm_client.chat(
            snapshot=snapshot,
            source=source,
            message=message,
            history=history,
        )
        with self._lock:
            if self._session is not None:
                self._session.append_chat_turn(
                    question=message,
                    reply=reply,
                    max_turns=self.max_chat_turns,
                )
                self.state_store.update_assistant_session(self._session)
        return reply

    def _should_start_new_session(self, snapshot: GameSnapshot) -> bool:
        if self._session is None:
            return True
        previous = self._last_snapshot
        if previous is None:
            return True
        if not previous.in_game:
            return True
        if (
            snapshot.character_class
            and previous.character_class
            and snapshot.character_class != previous.character_class
        ):
            return True
        if (
            snapshot.floor is not None
            and previous.floor is not None
            and snapshot.floor < previous.floor
        ):
            return True
        return False

    def _ensure_session(self, snapshot: GameSnapshot) -> None:
        if self._should_start_new_session(snapshot):
            self._session = AssistantSession(session_id=uuid4().hex)
        self._last_snapshot = snapshot

    def _no_state_reply(
        self,
        mode: str,
        source: str,
        message: str | None = None,
    ) -> AssistantReply:
        reasons = [
            "\u540e\u7aef\u8fd8\u6ca1\u6709\u6536\u5230\u4efb\u4f55\u5bf9\u5c40\u72b6\u6001\u3002",
            "\u8bf7\u5148\u542f\u52a8\u6e38\u620f\uff0c\u5e76\u8ba9 Communication Mod \u628a\u72b6\u6001\u63a8\u5230\u672c\u5730 API\u3002",
            "\u72b6\u6001\u8fde\u4e0a\u540e\uff0c\u8fd9\u91cc\u4f1a\u7acb\u523b\u663e\u793a\u4e2d\u6587\u7ed3\u8bba\u3001\u539f\u56e0\u548c\u5907\u9009\u3002",
        ]
        if mode == "chat" and message:
            reasons[0] = f"\u4f60\u7684\u95ee\u9898\u662f\uff1a{message[:60]}"
        return AssistantReply(
            mode=mode,
            source=source,
            conclusion="\u5f53\u524d\u8fd8\u6ca1\u6709\u6e38\u620f\u5bf9\u5c40\u53ef\u4ee5\u5206\u6790\u3002",
            reasons=reasons,
            alternatives=[],
            build_direction=None,
        )

    def _reply_from_recommendation(self, recommendation: RecommendationResult) -> AssistantReply:
        return AssistantReply(
            mode="analysis",
            source="auto",
            conclusion=self._conclusion_from_recommendation(recommendation),
            reasons=self._reason_lines_from_recommendation(recommendation),
            alternatives=recommendation.alternatives[:3],
            build_direction=recommendation.build_direction,
            raw_response={"recommendation": recommendation.to_dict()},
        )

    def _conclusion_from_recommendation(self, recommendation: RecommendationResult) -> str:
        action = recommendation.suggested_action.upper()
        target = recommendation.primary_target
        if action == "TAKE":
            return f"\u8fd9\u6b21\u5956\u52b1\u4f18\u5148\u62ff{target}\u3002" if target else "\u8fd9\u6b21\u5956\u52b1\u5efa\u8bae\u62ff\u724c\u3002"
        if action == "SKIP":
            return "\u8fd9\u6b21\u5956\u52b1\u66f4\u9002\u5408\u8df3\u8fc7\u3002"
        if action == "BOWL":
            return "\u8fd9\u6b21\u66f4\u9002\u5408\u62ff\u6c64\u63d0\u9ad8\u5bb9\u9519\u3002"
        if action == "BUY_CARD":
            return f"\u5546\u5e97\u91cc\u4f18\u5148\u4e70{target}\u3002" if target else "\u5546\u5e97\u91cc\u4f18\u5148\u4e70\u724c\u3002"
        if action == "BUY_RELIC":
            return f"\u5546\u5e97\u91cc\u4f18\u5148\u4e70{target}\u3002" if target else "\u5546\u5e97\u91cc\u4f18\u5148\u4e70\u9057\u7269\u3002"
        if action == "BUY_POTION":
            return f"\u5546\u5e97\u91cc\u53ef\u4ee5\u8865{target}\u3002" if target else "\u5546\u5e97\u91cc\u53ef\u4ee5\u8865\u4e00\u74f6\u836f\u6c34\u3002"
        if action == "REMOVE":
            return f"\u8fd9\u5bb6\u5546\u5e97\u4f18\u5148\u5220\u6389{target}\u3002" if target else "\u8fd9\u5bb6\u5546\u5e97\u4f18\u5148\u8003\u8651\u5220\u724c\u3002"
        if action == "LEAVE":
            return "\u8fd9\u5bb6\u5546\u5e97\u53ef\u4ee5\u5148\u4e0d\u82b1\u94b1\u3002"
        if action == "LLM_NOT_CONFIGURED":
            return "\u5f53\u524d\u8fd8\u6ca1\u6709\u914d\u7f6e\u6a21\u578b\uff0c\u52a9\u624b\u5148\u4fdd\u7559\u72b6\u6001\u6458\u8981\u3002"
        if action == "UNPARSEABLE_RESPONSE":
            return "\u6a21\u578b\u8fd9\u6b21\u6ca1\u6709\u7a33\u5b9a\u8fd4\u56de\u53ef\u7528\u7ed3\u679c\uff0c\u5148\u8d70\u4fdd\u5b88\u7ebf\u3002"
        return "\u5148\u6309\u5f53\u524d\u5c40\u9762\u8d70\u4fdd\u5b88\u7ebf\u3002"

    def _reason_lines_from_recommendation(self, recommendation: RecommendationResult) -> list[str]:
        raw = recommendation.reasoning.replace("\r\n", "\n").replace("\r", "\n")
        chunks = [item.strip(" -\t") for item in raw.split("\n") if item.strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for item in chunks:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= 4:
                break
        if recommendation.build_direction and len(deduped) < 2:
            deduped.append(f"\u6784\u7b51\u65b9\u5411\u504f\u5411\uff1a{recommendation.build_direction}\u3002")
        if len(deduped) < 2:
            deduped.append("\u8fd9\u662f\u5f53\u524d\u5c40\u9762\u4e0b\u66f4\u7a33\u7684\u53d6\u820d\u3002")
        return deduped[:4]
