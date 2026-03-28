from __future__ import annotations

from datetime import datetime, timezone
import logging
from threading import Lock
from uuid import uuid4

from sts_ai_assistant.llm.base import AssistantReply, AssistantSession, LLMClient, RecommendationResult
from sts_ai_assistant.parsing.models import GameSnapshot
from sts_ai_assistant.service.rule_based_advisor import RuleBasedAdvisor
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
        self.rule_based_advisor = RuleBasedAdvisor()

    def on_snapshot(self, snapshot: GameSnapshot) -> None:
        with self._lock:
            if not snapshot.in_game:
                self._session = None
                self._last_snapshot = snapshot
                self.state_store.update_assistant_session(None)
                self.state_store.update_diagnostics(
                    {
                        "llm_configured": self.llm_client.is_configured(),
                        "last_state_at": None,
                        "last_screen_type": None,
                        "recommendation_source": None,
                        "recommendation_action": None,
                        "has_combat_data": False,
                        "next_step": "进入一局游戏后，等待 Communication Mod 推送状态。",
                    }
                )
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
            self.state_store.update_diagnostics(self._diagnostics_from_snapshot(snapshot))

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
            diagnostics = self._diagnostics_from_snapshot(snapshot)
            diagnostics["recommendation_source"] = self._recommendation_source(recommendation)
            diagnostics["recommendation_action"] = recommendation.suggested_action.upper()
            self.state_store.update_diagnostics(diagnostics)
        return reply

    def analyze(self, source: str, focus: str | None = None) -> AssistantReply:
        snapshot = self.state_store.get_latest_snapshot()
        if snapshot is None or not snapshot.in_game:
            return self._no_state_reply(mode="analysis", source=source)

        fallback = self.rule_based_advisor.analyze(snapshot, source=source, focus=focus)
        with self._lock:
            self._ensure_session(snapshot)

        try:
            reply = self.llm_client.analyze(snapshot, source=source, focus=focus)
        except Exception as exc:
            self.logger.warning("Assistant analyze failed, fallback to rule advisor: %s", exc)
            if fallback is not None:
                reply = fallback
            else:
                raise
        reply = self._finalize_reply(snapshot, reply, fallback)
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

        fallback = self.rule_based_advisor.chat(
            snapshot=snapshot,
            source=source,
            message=message,
            history=history,
        )
        try:
            reply = self.llm_client.chat(
                snapshot=snapshot,
                source=source,
                message=message,
                history=history,
            )
        except Exception as exc:
            self.logger.warning("Assistant chat failed, fallback to rule advisor: %s", exc)
            if fallback is not None:
                reply = fallback
            else:
                raise
        reply = self._finalize_reply(snapshot, reply, fallback)
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
            if recommendation.screen_type.upper() in {"BOSS_REWARD", "COMBAT_REWARD", "TREASURE", "CHEST"}:
                return f"\u8fd9\u6b21\u9057\u7269\u9009\u62e9\u4f18\u5148\u62ff{target}\u3002" if target else "\u8fd9\u6b21\u9057\u7269\u9009\u62e9\u5efa\u8bae\u76f4\u63a5\u62ff\u3002"
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
        if action == "PLAY_SEQUENCE":
            return f"\u8fd9\u56de\u5408\u5148\u4ece{target}\u8d77\u624b\u3002" if target else "\u8fd9\u56de\u5408\u5148\u6309\u51cf\u4f24\u4f18\u5148\u987a\u5e8f\u51fa\u724c\u3002"
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

    def _finalize_reply(
        self,
        snapshot: GameSnapshot,
        reply: AssistantReply,
        fallback: AssistantReply | None,
    ) -> AssistantReply:
        if fallback is None:
            return reply

        screen_type = snapshot.context.screen_type.upper()
        if screen_type == "COMBAT":
            return fallback

        if self._looks_generic(reply) and fallback.conclusion:
            return fallback

        if len(reply.reasons) < 2:
            reply.reasons = fallback.reasons[:4]
        if not reply.alternatives:
            reply.alternatives = fallback.alternatives[:3]
        if not reply.build_direction:
            reply.build_direction = fallback.build_direction
        return reply

    def _looks_generic(self, reply: AssistantReply) -> bool:
        text = " ".join([reply.conclusion, *reply.reasons]).casefold()
        generic_markers = (
            "保守",
            "继续追问",
            "当前问题可以继续追问",
            "模型这次没有稳定返回结构化 json",
            "先按当前局面走稳",
            "先展示局面摘要",
            "当前未配置模型",
        )
        return any(marker.casefold() in text for marker in generic_markers)

    def _diagnostics_from_snapshot(self, snapshot: GameSnapshot) -> dict[str, object]:
        screen_type = snapshot.context.screen_type.upper()
        has_combat_data = bool(
            snapshot.context.screen_state.get("hand")
            or snapshot.context.screen_state.get("monsters")
            or snapshot.context.screen_state.get("energy") is not None
        )
        if not self.llm_client.is_configured():
            next_step = "先配置模型接口，当前建议会以规则兜底为主。"
        elif screen_type in {"UNKNOWN", "NONE"}:
            next_step = "进入奖励、商店或战斗等可分析界面后，再点击一键分析。"
        elif screen_type == "COMBAT" and not has_combat_data:
            next_step = "当前已识别为战斗，但还没收到手牌或敌人详情，先过一拍再刷新。"
        else:
            next_step = "状态链路正常，可以直接分析或提问。"
        return {
            "llm_configured": self.llm_client.is_configured(),
            "last_state_at": datetime.now(timezone.utc).isoformat(),
            "last_screen_type": screen_type,
            "recommendation_source": None,
            "recommendation_action": None,
            "has_combat_data": has_combat_data,
            "next_step": next_step,
        }

    def _recommendation_source(self, recommendation: RecommendationResult) -> str:
        raw = recommendation.raw_response
        if raw.get("rule_based"):
            return "规则兜底"
        if raw.get("provider_response"):
            return "模型"
        if raw.get("recommendation"):
            return "自动建议"
        return "未知"
