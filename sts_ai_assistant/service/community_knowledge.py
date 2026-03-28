from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from sts_ai_assistant.parsing.display_names import looks_garbled_text


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = ROOT / "data" / "community_knowledge.json"


@dataclass(frozen=True, slots=True)
class CommunitySource:
    source_id: str
    title: str
    url: str
    publisher: str
    published_at: str
    summary: str
    fetched_at: str = ""
    character_classes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    excerpt: str = ""
    raw_status: str = "fallback"


@dataclass(frozen=True, slots=True)
class CommunityGeneralNote:
    character_class: str
    min_floor: int
    max_floor: int
    build_direction: str
    reason_lines: tuple[str, ...]
    source_ids: tuple[str, ...]
    archetype_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommunityCardNote:
    character_class: str
    card_id: str
    min_floor: int
    max_floor: int
    score_adjustment: float
    build_direction: str
    reason_lines: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(slots=True)
class CommunityKnowledgeBase:
    data_path: Path = DEFAULT_DATA_PATH
    sources: dict[str, CommunitySource] = field(default_factory=dict)
    general_notes: list[CommunityGeneralNote] = field(default_factory=list)
    card_notes: list[CommunityCardNote] = field(default_factory=list)
    generated_at: str | None = None

    def __post_init__(self) -> None:
        self.load()

    def load(self) -> None:
        self.sources = {}
        self.general_notes = []
        self.card_notes = []
        self.generated_at = None

        if not self.data_path.exists():
            return

        raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        self.generated_at = self._as_text(raw.get("generated_at"))

        for item in raw.get("sources", []):
            if not isinstance(item, dict):
                continue
            source_id = self._as_text(item.get("source_id")) or "unknown_source"
            publisher = self._as_text(item.get("publisher")) or "Unknown publisher"
            source = CommunitySource(
                source_id=source_id,
                title=self._clean_source_text(self._as_text(item.get("title"))) or self._fallback_title(source_id, publisher),
                url=self._as_text(item.get("url")) or "",
                publisher=publisher,
                published_at=self._as_text(item.get("published_at")) or "unknown",
                summary=self._clean_source_text(self._as_text(item.get("summary"))) or "",
                fetched_at=self._as_text(item.get("fetched_at")) or "",
                character_classes=tuple(self._as_text_list(item.get("character_classes"))),
                tags=tuple(self._as_text_list(item.get("tags"))),
                excerpt=self._clean_source_text(self._as_text(item.get("excerpt"))) or "",
                raw_status=self._as_text(item.get("raw_status")) or "fallback",
            )
            self.sources[source.source_id] = source

        for item in raw.get("general_notes", []):
            if not isinstance(item, dict):
                continue
            self.general_notes.append(
                CommunityGeneralNote(
                    character_class=self._as_text(item.get("character_class")) or "",
                    min_floor=self._as_int(item.get("min_floor"), default=0),
                    max_floor=self._as_int(item.get("max_floor"), default=99),
                    build_direction=self._as_text(item.get("build_direction")) or "",
                    reason_lines=tuple(self._as_text_list(item.get("reason_lines"))),
                    source_ids=tuple(self._as_text_list(item.get("source_ids"))),
                    archetype_hints=tuple(self._as_text_list(item.get("archetype_hints"))),
                )
            )

        for item in raw.get("card_notes", []):
            if not isinstance(item, dict):
                continue
            self.card_notes.append(
                CommunityCardNote(
                    character_class=self._as_text(item.get("character_class")) or "",
                    card_id=self._as_text(item.get("card_id")) or "",
                    min_floor=self._as_int(item.get("min_floor"), default=0),
                    max_floor=self._as_int(item.get("max_floor"), default=99),
                    score_adjustment=self._as_float(item.get("score_adjustment"), default=0.0),
                    build_direction=self._as_text(item.get("build_direction")) or "",
                    reason_lines=tuple(self._as_text_list(item.get("reason_lines"))),
                    source_ids=tuple(self._as_text_list(item.get("source_ids"))),
                )
            )

    def general_note(
        self,
        character_class: str | None,
        floor: int,
    ) -> CommunityGeneralNote | None:
        normalized = (character_class or "").upper()
        for note in self.general_notes:
            if note.character_class != normalized:
                continue
            if note.min_floor <= floor <= note.max_floor:
                return note
        return None

    def card_note(
        self,
        character_class: str | None,
        card_id: str,
        floor: int,
    ) -> CommunityCardNote | None:
        normalized = (character_class or "").upper()
        for note in self.card_notes:
            if note.character_class != normalized:
                continue
            if note.card_id != card_id:
                continue
            if note.min_floor <= floor <= note.max_floor:
                return note
        return None

    def sources_for_ids(self, source_ids: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
        collected: list[dict[str, str]] = []
        for source_id in source_ids:
            source = self.sources.get(source_id)
            if source is None:
                continue
            if not any([source.title.strip(), source.summary.strip(), source.excerpt.strip()]):
                continue
            collected.append(
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "publisher": source.publisher,
                    "published_at": source.published_at,
                    "summary": source.summary,
                    "excerpt": source.excerpt,
                    "raw_status": source.raw_status,
                }
            )
        return collected

    def relevant_context(
        self,
        character_class: str | None,
        floor: int | None,
        card_ids: list[str] | None = None,
        limit_sources: int = 3,
    ) -> dict[str, object]:
        safe_floor = floor or 0
        general = self.general_note(character_class, safe_floor)
        card_notes: list[CommunityCardNote] = []
        seen_cards: set[str] = set()
        for card_id in card_ids or []:
            if card_id in seen_cards:
                continue
            seen_cards.add(card_id)
            note = self.card_note(character_class, card_id, safe_floor)
            if note is not None:
                card_notes.append(note)

        source_ids: list[str] = []
        if general is not None:
            source_ids.extend(general.source_ids)
        for note in card_notes:
            source_ids.extend(note.source_ids)
        deduped_source_ids = list(dict.fromkeys(source_ids))[:limit_sources]

        return {
            "generated_at": self.generated_at,
            "general_note": None
            if general is None
            else {
                "build_direction": general.build_direction,
                "reason_lines": list(general.reason_lines),
                "source_ids": list(general.source_ids),
                "archetype_hints": list(general.archetype_hints),
            },
            "card_notes": [
                {
                    "card_id": note.card_id,
                    "score_adjustment": note.score_adjustment,
                    "build_direction": note.build_direction,
                    "reason_lines": list(note.reason_lines),
                    "source_ids": list(note.source_ids),
                }
                for note in card_notes
            ],
            "sources": self.sources_for_ids(deduped_source_ids),
        }

    @staticmethod
    def _as_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _as_text_list(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        results: list[str] = []
        for item in value:
            text = cls._as_text(item)
            if text:
                results.append(text)
        return results

    @staticmethod
    def _as_int(value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clean_source_text(value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if looks_garbled_text(text):
            return None
        return text

    @classmethod
    def _fallback_title(cls, source_id: str, publisher: str) -> str:
        lowered = source_id.casefold()
        token_map = {
            "silent": "静默",
            "defect": "缺陷",
            "ironclad": "铁甲",
            "watcher": "观者",
            "corpse": "尸爆",
            "poison": "毒",
            "shiv": "刀流",
            "discard": "弃牌",
            "frost": "冰球",
            "focus": "聚焦",
            "dark": "黑球",
            "orb": "球体",
            "zero": "零费",
            "cost": "",
            "claw": "爪",
            "power": "能力",
            "corruption": "腐化",
            "exhaust": "废牌",
            "body": "Body",
            "slam": "Slam",
            "strength": "力量",
            "rushdown": "Rushdown",
            "scry": "占卜",
            "divinity": "天人",
            "route": "路线",
        }
        words: list[str] = []
        for token in lowered.replace("-", "_").split("_"):
            mapped = token_map.get(token, token)
            mapped = mapped.strip()
            if mapped and mapped not in words:
                words.append(mapped)
        fallback = "".join(words[:4]).strip()
        if fallback:
            return fallback
        if publisher == "Curated Community Notes":
            return "本地整理路线笔记"
        return "本地整理来源"
