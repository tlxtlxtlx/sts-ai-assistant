from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
from typing import Any

from sts_ai_assistant.parsing.display_names import looks_garbled_text

_CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk")


def decode_transport_bytes(raw: bytes) -> tuple[str, str]:
    best_text: str | None = None
    best_encoding = "utf-8"
    best_score: int | None = None

    for penalty, encoding in enumerate(_CANDIDATE_ENCODINGS):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue

        score = _score_candidate(text) - penalty
        if best_score is None or score > best_score:
            best_text = text
            best_encoding = encoding
            best_score = score

    if best_text is not None:
        return best_text, best_encoding

    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def _score_candidate(text: str) -> int:
    score = 0
    if "\ufffd" in text:
        score -= 200

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return score

    score += 100
    names = list(_iter_name_fields(payload))
    for name in names:
        if looks_garbled_text(name):
            score -= 25
        else:
            score += 10
            if any("\u4e00" <= char <= "\u9fff" for char in name):
                score += 2
    return score


def _iter_name_fields(payload: Any) -> Iterator[str]:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            lowered = str(key).casefold()
            if lowered in {"name", "display_name"} and isinstance(value, str):
                yield value
            else:
                yield from _iter_name_fields(value)
        return

    if isinstance(payload, list):
        for item in payload:
            yield from _iter_name_fields(item)
