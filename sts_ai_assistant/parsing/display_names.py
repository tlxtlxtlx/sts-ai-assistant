from __future__ import annotations

import re


CARD_NAME_OVERRIDES: dict[str, str] = {
    "Strike_R": "打击",
    "Strike_G": "打击",
    "Strike_B": "打击",
    "Strike_P": "打击",
    "Defend_R": "防御",
    "Defend_G": "防御",
    "Defend_B": "防御",
    "Defend_P": "防御",
    "Bash": "重击",
    "Neutralize": "中和",
    "Survivor": "幸存者",
    "Zap": "电击",
    "Dualcast": "双重施放",
    "Eruption": "爆发",
    "Vigilance": "警惕",
    "Underhanded Strike": "暗击",
    "Dodge and Roll": "闪避与翻滚",
    "Calculated Gamble": "计算赌注",
    "Acrobatics": "杂技",
    "Quick Slash": "快斩",
    "Beam Cell": "光束射线",
    "Coolheaded": "冷静头脑",
    "Genetic Algorithm": "遗传算法",
    "Stack": "堆栈",
}

RELIC_NAME_OVERRIDES: dict[str, str] = {
    "Burning Blood": "燃烧之血",
    "Ring of the Snake": "蛇之戒指",
    "PureWater": "圣水",
    "Pure Water": "圣水",
    "Cracked Core": "破损核心",
    "Juzu Bracelet": "念珠项链",
    "Maw Bank": "巨口储钱罐",
    "MawBank": "巨口储钱罐",
}

POTION_NAME_OVERRIDES: dict[str, str] = {}

_MOJIBAKE_MARKERS = (
    "锟",
    "鈥",
    "杩",
    "鍗",
    "閬",
    "绛",
    "鏈",
    "锛",
    "銆",
    "缁",
    "闂",
    "璇",
    "澶",
    "鐗",
    "娓",
    "濂",
    "宸",
    "鍏",
    "鍙",
    "鍟",
)

_SUSPICIOUS_NAME_PATTERN = re.compile(r"[^A-Za-z0-9\u4E00-\u9FFF\s_\-+.'&:/()（）【】·]")


def looks_garbled_text(value: str | None) -> bool:
    if value is None:
        return True

    text = value.strip()
    if not text:
        return True
    if "\ufffd" in text:
        return True
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        return True
    if _SUSPICIOUS_NAME_PATTERN.search(text):
        return True

    for ch in text:
        codepoint = ord(ch)
        if 0x0590 <= codepoint <= 0x08FF:
            return True

    return False


def resolve_card_name(card_id: str, raw_name: str | None) -> str:
    return _resolve_name(card_id, raw_name, CARD_NAME_OVERRIDES)


def resolve_relic_name(relic_id: str, raw_name: str | None) -> str:
    return _resolve_name(relic_id, raw_name, RELIC_NAME_OVERRIDES)


def resolve_potion_name(potion_id: str, raw_name: str | None) -> str:
    return _resolve_name(potion_id, raw_name, POTION_NAME_OVERRIDES)


def _resolve_name(item_id: str, raw_name: str | None, overrides: dict[str, str]) -> str:
    override = overrides.get(item_id)
    if override:
        return override

    if raw_name and not looks_garbled_text(raw_name):
        return raw_name.strip()

    return _prettify_identifier(item_id)


def _prettify_identifier(value: str) -> str:
    text = value.strip()
    if not text:
        return "UNKNOWN"
    if " " in text:
        return text

    compact = re.sub(r"[_-]+", " ", text)
    compact = re.sub(r"\b([RGBP])\b$", "", compact).strip()
    compact = re.sub(r"\s+", " ", compact)
    return compact or value
