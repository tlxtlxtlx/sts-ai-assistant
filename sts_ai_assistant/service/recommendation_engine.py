from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sts_ai_assistant.llm.base import LLMClient, RecommendationResult
from sts_ai_assistant.parsing.models import GameSnapshot
from sts_ai_assistant.service.rule_based_advisor import RuleBasedAdvisor


class JsonlRecommendationSink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, snapshot: GameSnapshot, recommendation: RecommendationResult) -> None:
        record = {
            "screen_type": snapshot.context.screen_type,
            "floor": snapshot.floor,
            "ascension_level": snapshot.ascension_level,
            "character_class": snapshot.character_class,
            "deck_size": len(snapshot.deck),
            "relics": snapshot.relic_names(),
            "recommendation": recommendation.to_dict(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class RecommendationEngine:
    TRIGGER_SCREENS = {
        "CARD_REWARD",
        "SHOP",
        "SHOP_SCREEN",
        "COMBAT",
        "BOSS_REWARD",
        "COMBAT_REWARD",
        "TREASURE",
        "CHEST",
    }

    def __init__(self, llm_client: LLMClient, sink: JsonlRecommendationSink) -> None:
        self.llm_client = llm_client
        self.sink = sink
        self._last_signature: str | None = None
        self.rule_based_advisor = RuleBasedAdvisor()

    def maybe_recommend(self, snapshot: GameSnapshot) -> RecommendationResult | None:
        screen_type = snapshot.context.screen_type.upper()
        if screen_type not in self.TRIGGER_SCREENS:
            self._last_signature = None
            return None

        signature = self._make_signature(snapshot)
        if signature == self._last_signature:
            return None

        self._last_signature = signature
        if screen_type == "COMBAT":
            recommendation = self.rule_based_advisor.recommend(snapshot)
            if recommendation is None:
                return None
        else:
            recommendation = self.llm_client.recommend(snapshot)
            recommendation = self._finalize_recommendation(snapshot, recommendation)
        self.sink.write(snapshot, recommendation)
        return recommendation

    def _make_signature(self, snapshot: GameSnapshot) -> str:
        stable_payload: dict[str, Any] = {
            "floor": snapshot.floor,
            "screen_type": snapshot.context.screen_type,
            "deck": [
                {
                    "id": card.id,
                    "upgrades": card.upgrades,
                    "misc": card.misc,
                }
                for card in snapshot.deck
            ],
            "relics": [relic.id for relic in snapshot.relics],
            "screen_state": snapshot.context.normalized_state(),
        }
        encoded = json.dumps(stable_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _finalize_recommendation(
        self,
        snapshot: GameSnapshot,
        recommendation: RecommendationResult,
    ) -> RecommendationResult:
        fallback = self.rule_based_advisor.recommend(snapshot)
        if fallback is None:
            return recommendation

        if snapshot.context.screen_type.upper() == "COMBAT":
            return fallback

        action = recommendation.suggested_action.upper().strip()
        if action in {"LLM_NOT_CONFIGURED", "UNPARSEABLE_RESPONSE", "UNKNOWN"}:
            return fallback

        if action == "TAKE" and not recommendation.primary_target:
            return fallback

        if action in {"SKIP", "BOWL"} and not recommendation.reasoning.strip():
            return fallback

        if not recommendation.reasoning.strip():
            recommendation.reasoning = fallback.reasoning
        if not recommendation.build_direction:
            recommendation.build_direction = fallback.build_direction
        if not recommendation.alternatives:
            recommendation.alternatives = fallback.alternatives
        return recommendation
