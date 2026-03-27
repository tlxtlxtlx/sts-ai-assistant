from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sts_ai_assistant.llm.base import LLMClient, RecommendationResult
from sts_ai_assistant.parsing.models import GameSnapshot


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
    TRIGGER_SCREENS = {"CARD_REWARD", "SHOP", "SHOP_SCREEN"}

    def __init__(self, llm_client: LLMClient, sink: JsonlRecommendationSink) -> None:
        self.llm_client = llm_client
        self.sink = sink
        self._last_signature: str | None = None

    def maybe_recommend(self, snapshot: GameSnapshot) -> RecommendationResult | None:
        if snapshot.context.screen_type.upper() not in self.TRIGGER_SCREENS:
            self._last_signature = None
            return None

        signature = self._make_signature(snapshot)
        if signature == self._last_signature:
            return None

        self._last_signature = signature
        recommendation = self.llm_client.recommend(snapshot)
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
