from __future__ import annotations

import json

from sts_ai_assistant.llm.base import ChatTurn
from sts_ai_assistant.parsing.models import GameSnapshot


ASSISTANT_JSON_RULES = (
    "你是《杀戮尖塔》的中文智能顾问。"
    "只根据提供的游戏状态回答。"
    "输出必须是原始 JSON，对象键固定为 conclusion、reasons、alternatives、build_direction。"
    "不要使用 Markdown，不要代码块，不要思维流，不要调试文本。"
    "conclusion 必须是一句简体中文短句。"
    "reasons 必须是 2 到 4 条简体中文短句数组。"
    "alternatives 必须是 0 到 3 条简短备选数组。"
    "build_direction 没有时返回 null。"
    "如果当前是战斗阶段，只能给出建议顺序、风险提醒和资源取舍，不能生成执行命令。"
)


def build_recommendation_messages(snapshot: GameSnapshot) -> list[dict[str, str]]:
    payload = snapshot.to_llm_payload()
    screen_type = snapshot.context.screen_type.upper()
    if screen_type == "CARD_REWARD":
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
