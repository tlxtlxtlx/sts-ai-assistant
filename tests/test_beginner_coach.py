from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from sts_ai_assistant.llm.openai_compatible import NullLLMClient
from sts_ai_assistant.parsing.models import (
    CardRewardState,
    CardSnapshot,
    GameSnapshot,
    RecommendationContext,
    RelicSnapshot,
)
from sts_ai_assistant.service.assistant_service import AssistantService
from sts_ai_assistant.service.rule_based_advisor import RuleBasedAdvisor
from sts_ai_assistant.service.state_store import LatestStateStore

TEST_OUTPUT_DIR = Path("tests") / ".tmp-beginner-coach"


def _silent_reward_snapshot() -> GameSnapshot:
    return GameSnapshot(
        in_game=True,
        ready_for_command=True,
        available_commands=["choose"],
        character_class="THE_SILENT",
        ascension_level=0,
        floor=3,
        act=1,
        gold=99,
        current_hp=63,
        max_hp=77,
        deck=[
            CardSnapshot(id="Neutralize", name="中和", cost=0, type="ATTACK", rarity="BASIC"),
            CardSnapshot(id="Survivor", name="幸存者", cost=1, type="SKILL", rarity="BASIC"),
            CardSnapshot(id="Strike_G", name="打击", cost=1, type="ATTACK", rarity="BASIC"),
            CardSnapshot(id="Strike_G", name="打击", cost=1, type="ATTACK", rarity="BASIC"),
            CardSnapshot(id="Strike_G", name="打击", cost=1, type="ATTACK", rarity="BASIC"),
            CardSnapshot(id="Strike_G", name="打击", cost=1, type="ATTACK", rarity="BASIC"),
            CardSnapshot(id="Strike_G", name="打击", cost=1, type="ATTACK", rarity="BASIC"),
            CardSnapshot(id="Defend_G", name="防御", cost=1, type="SKILL", rarity="BASIC"),
            CardSnapshot(id="Defend_G", name="防御", cost=1, type="SKILL", rarity="BASIC"),
            CardSnapshot(id="Defend_G", name="防御", cost=1, type="SKILL", rarity="BASIC"),
            CardSnapshot(id="Defend_G", name="防御", cost=1, type="SKILL", rarity="BASIC"),
            CardSnapshot(id="Defend_G", name="防御", cost=1, type="SKILL", rarity="BASIC"),
        ],
        relics=[RelicSnapshot(id="Ring of the Snake", name="蛇之戒指")],
        context=RecommendationContext(
            screen_type="CARD_REWARD",
            card_reward=CardRewardState(
                cards=[
                    CardSnapshot(
                        id="Underhanded Strike",
                        name="暗击",
                        cost=2,
                        type="ATTACK",
                        rarity="COMMON",
                    ),
                    CardSnapshot(
                        id="Dodge and Roll",
                        name="闪避与翻滚",
                        cost=1,
                        type="SKILL",
                        rarity="COMMON",
                    ),
                    CardSnapshot(
                        id="Calculated Gamble",
                        name="计算赌注",
                        cost=0,
                        type="SKILL",
                        rarity="UNCOMMON",
                    ),
                ],
                bowl_available=False,
                skip_available=True,
            ),
        ),
        raw_game_state={},
    )


class BeginnerCoachTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(TEST_OUTPUT_DIR, ignore_errors=True)

    def test_rule_based_card_reward_analysis_exposes_beginner_teaching_metadata(self) -> None:
        advisor = RuleBasedAdvisor()

        reply = advisor.analyze(_silent_reward_snapshot(), source="web")

        self.assertIsNotNone(reply)
        recommendation = reply.raw_response["recommendation"]
        raw = recommendation["raw_response"]
        self.assertTrue(raw["learning_rule"])
        self.assertTrue(raw["fills_gap"])
        self.assertTrue(raw["safe_default"])

    def test_assistant_chat_answers_build_gap_question_without_generic_stub(self) -> None:
        snapshot = _silent_reward_snapshot()
        store = LatestStateStore(TEST_OUTPUT_DIR / "gap-state.json")
        store.update_snapshot(snapshot)
        service = AssistantService(NullLLMClient(), store)

        reply = service.chat(source="web", message="我现在这套牌缺什么？")

        self.assertNotIn("局面摘要", reply.conclusion)
        self.assertNotIn("当前未配置模型", reply.conclusion)
        self.assertGreaterEqual(len(reply.reasons), 2)
        self.assertTrue(reply.conclusion.startswith("当前这套牌最缺"))
        self.assertTrue(any("接下来" in reason or "下一步" in reason or "优先找" in reason for reason in reply.reasons))

    def test_assistant_chat_explains_why_not_remove_cards_yet(self) -> None:
        snapshot = _silent_reward_snapshot()
        store = LatestStateStore(TEST_OUTPUT_DIR / "remove-state.json")
        store.update_snapshot(snapshot)
        service = AssistantService(NullLLMClient(), store)

        reply = service.chat(source="web", message="为什么不删牌")

        self.assertNotIn("局面摘要", reply.conclusion)
        self.assertNotIn("当前未配置模型", reply.conclusion)
        self.assertGreaterEqual(len(reply.reasons), 2)
        self.assertIn("现在先不急着删牌", reply.conclusion)
        self.assertTrue(any("商店" in reason or "当前不是" in reason or "这层" in reason for reason in reply.reasons))


if __name__ == "__main__":
    unittest.main()
