from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib import request
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "community_knowledge.seed.json"
OUTPUT_PATH = ROOT / "data" / "community_knowledge.json"
CACHE_DIR = ROOT / "data" / "community_cache"

DEFAULT_HEADERS = {
    "Accept-Encoding": "identity",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
}

CARD_PATTERNS: dict[str, tuple[str, ...]] = {
    "Dodge and Roll": ("dodge and roll", "dash and roll", "block", "safe", "survive"),
    "Acrobatics": ("acrobatics", "draw", "discard", "cycle"),
    "Quick Slash": ("quick slash", "draw", "tempo"),
    "Calculated Gamble": ("calculated gamble", "discard", "cycle", "draw"),
    "Beam Cell": ("beam cell", "vulnerable", "zero cost"),
    "Coolheaded": ("coolheaded", "frost", "draw", "focus"),
    "Genetic Algorithm": ("genetic algorithm", "scaling block", "block"),
    "Stack": ("stack", "block", "defect"),
    "PommelStrike": ("pommel strike", "draw", "damage"),
    "ShrugItOff": ("shrug it off", "block", "draw"),
    "Inflame": ("inflame", "strength", "scaling"),
}

GENERAL_RULES: dict[str, dict[str, Any]] = {
    "THE_SILENT": {
        "min_floor": 0,
        "max_floor": 18,
        "build_direction": "社区共识通常是先稳住血线、补过牌和防御，再按奖励往毒、弃牌或刀流转。",
        "reason_lines": [
            "静默第一幕最怕回合发僵和白掉血，所以很多社区建议先补稳牌，再决定主流派。",
            "只要前期把节奏撑住，静默后续无论转毒、弃牌还是刀流都还有空间。",
        ],
        "archetype_hints": ["毒控制", "弃牌运转", "刀流节奏", "敏捷龟甲"],
    },
    "IRONCLAD": {
        "min_floor": 0,
        "max_floor": 18,
        "build_direction": "社区共识通常是先补第一幕战力和过牌，再看力量、废牌还是壁垒格挡哪条线更自然。",
        "reason_lines": [
            "铁甲前期能不能稳定打过精英，比空谈后期成长更关键。",
            "很多玩家会先抓高质量攻防牌，把回合质量做起来，再接力量或废牌组件。",
        ],
        "archetype_hints": ["力量爆发", "废牌引擎", "壁垒叠甲", "伤口联动"],
    },
    "DEFECT": {
        "min_floor": 0,
        "max_floor": 18,
        "build_direction": "社区共识通常是先补球体效率和防守手感，再看是走冰球聚焦、黑球爆发还是零费循环。",
        "reason_lines": [
            "机器人前期如果球体效率和防守都不顺，很容易还没成型就先掉太多血。",
            "先拿能改善回合质量的球体牌，通常比一开始硬赌高上限组件更稳。",
        ],
        "archetype_hints": ["冰球聚焦", "黑球爆发", "球体节奏", "零费回收"],
    },
    "WATCHER": {
        "min_floor": 0,
        "max_floor": 18,
        "build_direction": "社区共识通常是先保证姿态切换安全，再决定是走姿态爆发、占卜控制还是印记特化。",
        "reason_lines": [
            "观者最怕的是为了爆发硬进怒却退不出来，所以前期要先把安全性补出来。",
            "只要退怒和抽牌足够顺，观者后续很容易转成高上限路线。",
        ],
        "archetype_hints": ["姿态爆发", "Rushdown 连段", "占卜控制", "印记特化"],
    },
}

CARD_RULES: dict[tuple[str, str], dict[str, Any]] = {
    ("THE_SILENT", "Dodge and Roll"): {
        "min_floor": 0,
        "max_floor": 24,
        "score_adjustment": 0.42,
        "build_direction": "社区通常把它当静默前期最稳的防守补件之一，拿了以后更容易往敏捷龟甲或稳健过渡走。",
        "reason_lines": [
            "很多玩家会把闪避与翻滚当成静默第一幕很舒服的保血牌。",
            "它既能顶住前期压力，也不会妨碍后续转毒或弃牌。",
        ],
    },
    ("THE_SILENT", "Acrobatics"): {
        "min_floor": 0,
        "max_floor": 30,
        "score_adjustment": 0.36,
        "build_direction": "社区通常把它视为静默通用过牌骨架，拿了以后更容易往弃牌运转或毒控制走。",
        "reason_lines": [
            "杂技在很多静默讨论里都被看作高质量过牌件。",
            "它会明显提升回合选择质量，也方便后续接弃牌收益牌。",
        ],
    },
    ("THE_SILENT", "Quick Slash"): {
        "min_floor": 0,
        "max_floor": 18,
        "score_adjustment": 0.14,
        "build_direction": "社区更常把它当成前期节奏补丁，而不是必须围绕它构筑。",
        "reason_lines": [
            "快斩属于顺手的一费小补强，能补一点输出和过牌。",
            "它不太定义路线，但在第一幕经常够用。",
        ],
    },
    ("DEFECT", "Beam Cell"): {
        "min_floor": 0,
        "max_floor": 18,
        "score_adjustment": 0.2,
        "build_direction": "社区通常把它当零费节奏件，适合补前期效率，再看后续转球体还是零费循环。",
        "reason_lines": [
            "光束射线在很多讨论里都被视为很顺手的前期零费牌。",
            "球体体系还没齐时，它能先把易伤和节奏补上。",
        ],
    },
    ("DEFECT", "Coolheaded"): {
        "min_floor": 0,
        "max_floor": 24,
        "score_adjustment": 0.34,
        "build_direction": "社区通常把它视为冰球聚焦和稳健过渡的优质底盘。",
        "reason_lines": [
            "冷静头脑兼顾防守、抽牌和球体推进，很多玩家都很愿意早拿。",
            "它会让机器人更快进入稳定回合。",
        ],
    },
    ("DEFECT", "Genetic Algorithm"): {
        "min_floor": 0,
        "max_floor": 24,
        "score_adjustment": 0.24,
        "build_direction": "社区通常把它当成长型防御投资，前提是当前局面已经能扛住。",
        "reason_lines": [
            "遗传算法的上限不低，但更像提前布局未来的牌。",
            "如果当前血线和战力还行，提早拿会比较赚。",
        ],
    },
    ("DEFECT", "Stack"): {
        "min_floor": 0,
        "max_floor": 22,
        "score_adjustment": 0.08,
        "build_direction": "社区更常把它当特定防御结构的补件，而不是无脑抓的万能牌。",
        "reason_lines": [
            "堆栈的价值很看牌组厚度和抽牌结构。",
            "如果还没建立稳定防守和过牌，它不一定比通用好牌更值。",
        ],
    },
    ("IRONCLAD", "PommelStrike"): {
        "min_floor": 0,
        "max_floor": 20,
        "score_adjustment": 0.24,
        "build_direction": "社区通常把它视为铁甲第一幕高质量即战力，适合先稳住输出和抽牌节奏。",
        "reason_lines": [
            "它是很经典的铁甲前期好牌，输出和过牌都不亏。",
            "第一幕先把它这类实战牌拿稳，通常比空等后期件更靠谱。",
        ],
    },
    ("IRONCLAD", "ShrugItOff"): {
        "min_floor": 0,
        "max_floor": 22,
        "score_adjustment": 0.24,
        "build_direction": "社区通常把它视为铁甲最稳的防御过牌件之一，适合很多路线。",
        "reason_lines": [
            "耸肩无视在铁甲讨论里一直是稳健高分牌。",
            "它既保血又修手，很适合过第一幕。",
        ],
    },
    ("IRONCLAD", "Inflame"): {
        "min_floor": 0,
        "max_floor": 20,
        "score_adjustment": 0.08,
        "build_direction": "社区通常把它当力量路线的成长件，但会提醒别为了它放掉前期即时强度。",
        "reason_lines": [
            "燃烧之力代表的是后续成长，不是立刻解局面。",
            "前几层如果还在补战力，它往往没那么优先。",
        ],
    },
}


@dataclass(slots=True)
class CommunitySource:
    source_id: str
    title: str
    url: str
    publisher: str
    published_at: str
    summary: str
    fetched_at: str
    character_classes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    excerpt: str = ""
    raw_status: str = "fallback"


@dataclass(slots=True)
class CommunityGeneralNote:
    character_class: str
    min_floor: int
    max_floor: int
    build_direction: str
    reason_lines: list[str]
    source_ids: list[str]
    archetype_hints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CommunityCardNote:
    character_class: str
    card_id: str
    min_floor: int
    max_floor: int
    score_adjustment: float
    build_direction: str
    reason_lines: list[str]
    source_ids: list[str]


@dataclass(slots=True)
class CachedFetch:
    title: str
    summary: str
    excerpt: str
    published_at: str
    fetched_at: str
    raw_status: str


def load_seed() -> dict[str, Any]:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def _cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _load_cache(url: str) -> CachedFetch | None:
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return CachedFetch(
        title=str(raw.get("title") or "").strip(),
        summary=str(raw.get("summary") or "").strip(),
        excerpt=str(raw.get("excerpt") or "").strip(),
        published_at=str(raw.get("published_at") or "unknown").strip() or "unknown",
        fetched_at=str(raw.get("fetched_at") or "").strip(),
        raw_status=str(raw.get("raw_status") or "cache").strip() or "cache",
    )


def _write_cache(url: str, payload: CachedFetch) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(url)
    path.write_text(
        json.dumps(asdict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_html(url: str) -> str:
    req = request.Request(url, headers=DEFAULT_HEADERS)
    with request.urlopen(req, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def should_fetch_url(url: str) -> bool:
    return not url.startswith("https://community.local/")


def clean_html_text(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(html: str, fallback: str) -> str:
    match = re.search(r"(?is)<title>(.*?)</title>", html)
    if not match:
        return fallback
    title = clean_html_text(match.group(1))
    return title or fallback


def _looks_binary_garbled(text: str) -> bool:
    if not text:
        return False
    sample = text[:1200]
    control_count = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\r\n\t")
    replacement_count = sample.count("�")
    return control_count > 8 or replacement_count > 18


def summarize_source(text: str, classes: list[str], tags: list[str], fallback_summary: str | None = None) -> str:
    lowered = text.casefold()
    chunks: list[str] = []

    if "silent" in lowered or "静默" in lowered:
        chunks.append("更强调先稳住血线和回合质量，再顺势转毒、弃牌或刀流。")
    if "defect" in lowered or "机器人" in lowered or "orb" in lowered or "focus" in lowered:
        chunks.append("更看重球体效率、防守过渡和聚焦成长的平衡。")
    if "watcher" in lowered or "stance" in lowered or "rushdown" in lowered:
        chunks.append("更强调姿态切换的安全性，以及爆发与退怒之间的平衡。")
    if "ironclad" in lowered or "strength" in lowered or "exhaust" in lowered:
        chunks.append("通常建议先补第一幕战力，再决定力量、废牌还是壁垒格挡。")
    if "draw" in lowered or "cycle" in lowered or "discard" in lowered:
        chunks.append("资料里多次提到过牌和运转质量对稳定通关很关键。")
    if "block" in lowered or "defense" in lowered or "survive" in lowered:
        chunks.append("普遍强调第一幕先少掉血，比贪高上限更重要。")

    if not chunks and fallback_summary:
        return fallback_summary.strip()

    if not chunks:
        if "discussion" in tags or "search" in tags:
            chunks.append("这份社区资料更像玩家经验汇总，适合拿来补强卡牌评价和构筑倾向。")
        else:
            chunks.append("这份社区资料提供了可用于卡牌取舍和构筑方向判断的经验。")

    class_text = " / ".join(classes) if classes else "通用"
    return f"{class_text}向资料。{' '.join(dict.fromkeys(chunks))}"


def infer_published_at(text: str) -> str | None:
    match = re.search(r"\b(20\d{2}[-/\.]\d{1,2}[-/\.]\d{1,2})\b", text)
    if match:
        return match.group(1).replace("/", "-").replace(".", "-")
    match = re.search(r"\b(20\d{2})\b", text)
    if match:
        return match.group(1)
    return None


def build_source_entry(seed_source: dict[str, Any]) -> CommunitySource:
    fetched_at = datetime.now(UTC).isoformat()
    url = seed_source["url"]
    fallback_title = str(seed_source.get("fallback_title") or seed_source["source_id"])
    fallback_excerpt = str(seed_source.get("fallback_excerpt") or "").strip()
    fallback_summary = summarize_source(
        text=fallback_excerpt,
        classes=list(seed_source.get("character_classes") or []),
        tags=list(seed_source.get("tags") or []),
        fallback_summary=str(seed_source.get("fallback_summary") or "").strip() or None,
    )
    fallback_published_at = str(seed_source.get("fallback_published_at") or "unknown").strip() or "unknown"
    cached = _load_cache(url)

    if cached is not None:
        return CommunitySource(
            source_id=seed_source["source_id"],
            title=cached.title or fallback_title,
            url=url,
            publisher=seed_source["publisher"],
            published_at=cached.published_at or fallback_published_at,
            summary=cached.summary or fallback_summary,
            fetched_at=cached.fetched_at or fetched_at,
            character_classes=list(seed_source.get("character_classes") or []),
            tags=list(seed_source.get("tags") or []),
            excerpt=cached.excerpt or fallback_excerpt,
            raw_status=cached.raw_status or ("fallback" if not should_fetch_url(url) else "cache"),
        )

    if not should_fetch_url(url):
        cache_payload = CachedFetch(
            title=fallback_title,
            summary=fallback_summary,
            excerpt=fallback_excerpt,
            published_at=fallback_published_at,
            fetched_at=fetched_at,
            raw_status="fallback",
        )
        _write_cache(url, cache_payload)
        return CommunitySource(
            source_id=seed_source["source_id"],
            title=fallback_title,
            url=url,
            publisher=seed_source["publisher"],
            published_at=fallback_published_at,
            summary=fallback_summary,
            fetched_at=fetched_at,
            character_classes=list(seed_source.get("character_classes") or []),
            tags=list(seed_source.get("tags") or []),
            excerpt=fallback_excerpt,
            raw_status="fallback",
        )

    try:
        html = fetch_html(url)
        title = extract_title(html, fallback_title)
        text = clean_html_text(html)
        if _looks_binary_garbled(text):
            raise ValueError("garbled content")
        excerpt = text[:1200] or fallback_excerpt
        summary = summarize_source(
            text=text,
            classes=list(seed_source.get("character_classes") or []),
            tags=list(seed_source.get("tags") or []),
            fallback_summary=fallback_summary,
        )
        published_at = infer_published_at(text) or fallback_published_at
        cache_payload = CachedFetch(
            title=title,
            summary=summary,
            excerpt=excerpt,
            published_at=published_at,
            fetched_at=fetched_at,
            raw_status="fetched",
        )
        _write_cache(url, cache_payload)
        return CommunitySource(
            source_id=seed_source["source_id"],
            title=title,
            url=url,
            publisher=seed_source["publisher"],
            published_at=published_at,
            summary=summary,
            fetched_at=fetched_at,
            character_classes=list(seed_source.get("character_classes") or []),
            tags=list(seed_source.get("tags") or []),
            excerpt=excerpt,
            raw_status="fetched",
        )
    except (URLError, TimeoutError, ValueError) as exc:
        summary = f"{fallback_summary} ??????????????????????"
        cache_payload = CachedFetch(
            title=fallback_title,
            summary=summary,
            excerpt=fallback_excerpt,
            published_at=fallback_published_at,
            fetched_at=fetched_at,
            raw_status="fallback",
        )
        _write_cache(url, cache_payload)
        print(f"WARN fetch failed for {url}: {exc}")
        return CommunitySource(
            source_id=seed_source["source_id"],
            title=fallback_title,
            url=url,
            publisher=seed_source["publisher"],
            published_at=fallback_published_at,
            summary=summary,
            fetched_at=fetched_at,
            character_classes=list(seed_source.get("character_classes") or []),
            tags=list(seed_source.get("tags") or []),
            excerpt=fallback_excerpt,
            raw_status="fallback",
        )

def build_general_notes(source_entries: list[CommunitySource]) -> list[CommunityGeneralNote]:
    source_index = {entry.source_id: entry for entry in source_entries}
    results: list[CommunityGeneralNote] = []
    for character_class, rule in GENERAL_RULES.items():
        source_ids = [
            entry.source_id
            for entry in source_entries
            if character_class in entry.character_classes
        ]
        if not source_ids:
            source_ids = list(source_index)[:2]
        results.append(
            CommunityGeneralNote(
                character_class=character_class,
                min_floor=rule["min_floor"],
                max_floor=rule["max_floor"],
                build_direction=rule["build_direction"],
                reason_lines=list(rule["reason_lines"]),
                source_ids=source_ids[:3],
                archetype_hints=list(rule.get("archetype_hints") or []),
            )
        )
    return results


def build_card_notes(source_entries: list[CommunitySource]) -> list[CommunityCardNote]:
    source_texts = {entry.source_id: entry.excerpt.casefold() for entry in source_entries}
    results: list[CommunityCardNote] = []
    for (character_class, card_id), rule in CARD_RULES.items():
        matched_sources: list[str] = []
        for source in source_entries:
            if character_class not in source.character_classes:
                continue
            excerpt = source_texts[source.source_id]
            patterns = CARD_PATTERNS.get(card_id, ())
            if any(pattern in excerpt for pattern in patterns):
                matched_sources.append(source.source_id)
        if not matched_sources:
            matched_sources = [
                entry.source_id
                for entry in source_entries
                if character_class in entry.character_classes
            ][:2]
        results.append(
            CommunityCardNote(
                character_class=character_class,
                card_id=card_id,
                min_floor=rule["min_floor"],
                max_floor=rule["max_floor"],
                score_adjustment=rule["score_adjustment"],
                build_direction=rule["build_direction"],
                reason_lines=list(rule["reason_lines"]),
                source_ids=matched_sources[:3],
            )
        )
    return results


def main() -> int:
    seed = load_seed()
    source_entries = [build_source_entry(item) for item in seed.get("sources", [])]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": [asdict(item) for item in source_entries],
        "general_notes": [asdict(item) for item in build_general_notes(source_entries)],
        "card_notes": [asdict(item) for item in build_card_notes(source_entries)],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"WROTE {OUTPUT_PATH}")
    print(f"SOURCES {len(payload['sources'])}")
    print(f"GENERAL_NOTES {len(payload['general_notes'])}")
    print(f"CARD_NOTES {len(payload['card_notes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())