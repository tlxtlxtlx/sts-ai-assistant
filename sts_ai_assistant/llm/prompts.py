from __future__ import annotations

import json

from sts_ai_assistant.llm.base import ChatTurn
from sts_ai_assistant.parsing.models import GameSnapshot
from sts_ai_assistant.service.build_profile import BuildProfileEvaluator
from sts_ai_assistant.service.community_knowledge import CommunityKnowledgeBase


ASSISTANT_JSON_RULES = (
    "你是《杀戮尖塔》的中文智能顾问。"
    "只根据提供的游戏状态回答。"
    "输出必须是原始 JSON，对象键固定为 conclusion、reasons、alternatives、build_direction。"
    "不要使用 Markdown，不要代码块，不要思维流，不要调试文本。"
    "conclusion 必须是一句简体中文短句。"
    "reasons 必须是 2 到 4 条简体中文短句数组。"
    "alternatives 必须是 0 到 3 条简短备选数组。"
    "build_direction 没有时返回 null。"
    "如果当前是卡牌奖励，结论和原因必须明确回答推荐拿哪张牌或跳过。"
    "如果当前有 build_profile，优先说明这张牌是否契合当前构筑、拿了以后会往哪条路线走、如果跳过是在保什么路线。"
    "如果当前是战斗，优先说明推荐操作顺序、风险点、能量和格挡取舍。"
    "所有用户可见内容都要像游戏助手，不要像模型调试面板。"
    "如果当前是战斗阶段，只能给出建议顺序、风险提醒和资源取舍，不能生成执行命令。"
)

COMMUNITY_KNOWLEDGE = CommunityKnowledgeBase()
BUILD_PROFILE_EVALUATOR = BuildProfileEvaluator()


def _community_context(snapshot: GameSnapshot) -> dict[str, object]:
    candidate_card_ids: list[str] = []
    if snapshot.context.card_reward is not None:
        candidate_card_ids.extend(card.id for card in snapshot.context.card_reward.cards)
    if snapshot.context.shop is not None:
        candidate_card_ids.extend(card.id for card in snapshot.context.shop.cards)
    candidate_card_ids.extend(card.id for card in snapshot.deck[:12])
    return COMMUNITY_KNOWLEDGE.relevant_context(
        character_class=snapshot.character_class,
        floor=snapshot.floor,
        card_ids=candidate_card_ids,
    )


def _build_profile(snapshot: GameSnapshot) -> dict[str, object]:
    return BUILD_PROFILE_EVALUATOR.evaluate(snapshot).to_dict()


def build_recommendation_messages(snapshot: GameSnapshot) -> list[dict[str, str]]:
    payload = {
        "game_state": snapshot.to_llm_payload(),
        "community_context": _community_context(snapshot),
        "build_profile": _build_profile(snapshot),
    }
    screen_type = snapshot.context.screen_type.upper()
    if screen_type in {"CARD_REWARD", "BOSS_REWARD", "COMBAT_REWARD", "TREASURE", "CHEST"}:
        action_hint = "For suggested_action, choose one of TAKE, SKIP, or BOWL."
    else:
        action_hint = (
            "For suggested_action, choose one of BUY_CARD, BUY_RELIC, BUY_POTION, "
            "REMOVE, or LEAVE."
        )

    return [
        {
            "role": "system",
            "content": (
                "You are a Slay the Spire deck-building assistant. "
                "Use only the supplied game state. "
                f"{action_hint} "
                "Return raw JSON only, without markdown fences or chain-of-thought. "
                "Required keys: suggested_action, primary_target, build_direction, reasoning, alternatives. "
                "The suggested_action value must remain the English action code. "
                "primary_target should be the exact card/relic/potion name when applicable. "
                "build_direction and reasoning must be written in Simplified Chinese. "
                "alternatives should be a short array of other reasonable options, and may keep original in-game names. "
                "Keep the reasoning concise and practical. "
                "When the screen is CARD_REWARD, be explicit about which card to take or whether to skip. "
                "Use the supplied build_profile to explain whether the choice fits the current build, what route it pushes toward, "
                "and what route is preserved if you skip. "
                "Do not reveal internal reasoning or debugging text."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]


def build_analysis_messages(
    snapshot: GameSnapshot,
    source: str,
    focus: str | None = None,
) -> list[dict[str, str]]:
    payload = {
        "source": source,
        "focus": focus,
        "game_state": snapshot.to_llm_payload(),
        "community_context": _community_context(snapshot),
        "build_profile": _build_profile(snapshot),
    }
    return [
        {
            "role": "system",
            "content": ASSISTANT_JSON_RULES,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]


def build_chat_messages(
    snapshot: GameSnapshot,
    source: str,
    message: str,
    history: list[ChatTurn] | None = None,
) -> list[dict[str, str]]:
    recent_history = [
        {
            "question": turn.question,
            "reply": {
                "conclusion": turn.reply.conclusion,
                "reasons": turn.reply.reasons,
                "alternatives": turn.reply.alternatives,
                "build_direction": turn.reply.build_direction,
            },
        }
        for turn in (history or [])[-8:]
    ]
    payload = {
        "source": source,
        "question": message,
        "recent_history": recent_history,
        "game_state": snapshot.to_llm_payload(),
        "community_context": _community_context(snapshot),
        "build_profile": _build_profile(snapshot),
    }
    return [
        {
            "role": "system",
            "content": ASSISTANT_JSON_RULES,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]
