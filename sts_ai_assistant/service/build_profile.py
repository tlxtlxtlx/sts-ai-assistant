from __future__ import annotations

from dataclasses import dataclass, field

from sts_ai_assistant.parsing.display_names import resolve_card_name
from sts_ai_assistant.parsing.models import GameSnapshot
from sts_ai_assistant.service.community_knowledge import CommunityKnowledgeBase


@dataclass(slots=True)
class BuildOption:
    key: str
    name: str
    rating: str
    tier_label: str
    score: float
    summary: str
    core_cards: list[str]
    support_cards: list[str]
    missing_pieces: list[str]
    strengths: list[str]
    risks: list[str]
    next_picks: list[str]
    pivot_reason: str
    source_tags: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    community_summary: str | None = None
    community_sources: list[dict[str, str]] = field(default_factory=list)
    recommended_now: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "rating": self.rating,
            "tier_label": self.tier_label,
            "score": round(self.score, 3),
            "summary": self.summary,
            "core_cards": self.core_cards,
            "support_cards": self.support_cards,
            "missing_pieces": self.missing_pieces,
            "strengths": self.strengths,
            "risks": self.risks,
            "next_picks": self.next_picks,
            "pivot_reason": self.pivot_reason,
            "source_tags": self.source_tags,
            "source_ids": self.source_ids,
            "community_summary": self.community_summary,
            "community_sources": self.community_sources,
            "recommended_now": self.recommended_now,
        }


@dataclass(slots=True)
class BuildProfile:
    name: str
    rating: str
    tier_label: str
    score: float
    summary: str
    core_cards: list[str]
    support_cards: list[str]
    missing_pieces: list[str]
    strengths: list[str]
    risks: list[str]
    next_picks: list[str]
    archetype_key: str = "generic"
    source_tags: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    community_summary: str | None = None
    community_sources: list[dict[str, str]] = field(default_factory=list)
    alternatives: list[BuildOption] = field(default_factory=list)
    route_stage: str | None = None
    two_fight_goal: list[str] = field(default_factory=list)
    pivot_triggers: list[str] = field(default_factory=list)
    avoid_now: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "rating": self.rating,
            "tier_label": self.tier_label,
            "score": round(self.score, 3),
            "summary": self.summary,
            "core_cards": self.core_cards,
            "support_cards": self.support_cards,
            "missing_pieces": self.missing_pieces,
            "strengths": self.strengths,
            "risks": self.risks,
            "next_picks": self.next_picks,
            "archetype_key": self.archetype_key,
            "source_tags": self.source_tags,
            "source_ids": self.source_ids,
            "community_summary": self.community_summary,
            "community_sources": self.community_sources,
            "alternatives": [item.to_dict() for item in self.alternatives],
            "route_stage": self.route_stage,
            "two_fight_goal": self.two_fight_goal,
            "pivot_triggers": self.pivot_triggers,
            "avoid_now": self.avoid_now,
        }


class BuildProfileEvaluator:
    def __init__(self) -> None:
        self.community = CommunityKnowledgeBase()

    def evaluate(self, snapshot: GameSnapshot) -> BuildProfile:
        counts = self._deck_counts(snapshot)
        character = (snapshot.character_class or "").upper()

        if character == "THE_SILENT":
            return self._evaluate_silent(snapshot, counts)
        if character == "DEFECT":
            return self._evaluate_defect(snapshot, counts)
        if character == "IRONCLAD":
            return self._evaluate_ironclad(snapshot, counts)
        if character == "WATCHER":
            return self._evaluate_watcher(snapshot, counts)
        return self._evaluate_generic(snapshot)

    def _evaluate_silent(self, snapshot: GameSnapshot, counts: dict[str, int]) -> BuildProfile:
        options = [
            self._build_option(
                key="silent_corpse_poison",
                name="静默尸爆毒",
                score=0.18
                + self._sum_counts(counts, ["Corpse Explosion", "Catalyst", "Noxious Fumes", "Crippling Cloud"]) * 0.21
                + self._sum_counts(counts, ["Acrobatics", "Backflip", "Well Laid Plans", "Leg Sweep"]) * 0.05,
                summary="围绕尸爆、催化和持续上毒滚长战，清精英和首领时上限非常高。",
                core_cards=self._collect_present(counts, ["Corpse Explosion", "Catalyst", "Noxious Fumes", "Crippling Cloud", "Bouncing Flask"]),
                support_cards=self._collect_present(counts, ["Acrobatics", "Backflip", "Well Laid Plans", "Leg Sweep", "Dodge and Roll"]),
                missing_pieces=self._missing(["Corpse Explosion", "Catalyst", "稳定防御"], counts),
                strengths=["打双体和高血怪很强", "首领战终局感足", "成型后很适合慢慢滚死对手"],
                risks=["没毒核时前几回合偏慢", "很吃过牌和留牌质量", "前期容易因为贪上限掉血"],
                next_picks=["Catalyst", "Acrobatics", "Leg Sweep", "Well Laid Plans"],
                pivot_reason="如果已经摸到尸爆、催化或毒云，这条线比普通毒套更像真正的终局路线。",
                source_tags=["社区毒套", "尸爆毒", "高上限"],
                source_ids=["silent_corpse_poison_route", "reddit_silent_archetypes", "reddit_mastering_silent"],
            ),
            self._build_option(
                key="silent_poison_control",
                name="静默毒控制",
                score=0.2
                + self._sum_counts(counts, ["Deadly Poison", "Bouncing Flask", "Noxious Fumes", "Catalyst", "Crippling Cloud"]) * 0.18
                + self._sum_counts(counts, ["Acrobatics", "Backflip", "Leg Sweep", "Well Laid Plans"]) * 0.05,
                summary="靠上毒、拖回合和放大毒伤取胜，成型比尸爆毒更平滑，也更容易稳过渡。",
                core_cards=self._collect_present(counts, ["Deadly Poison", "Bouncing Flask", "Noxious Fumes", "Catalyst", "Crippling Cloud"]),
                support_cards=self._collect_present(counts, ["Acrobatics", "Backflip", "Leg Sweep", "Well Laid Plans", "Dodge and Roll"]),
                missing_pieces=self._missing(["Catalyst", "Noxious Fumes", "Leg Sweep"], counts),
                strengths=["长战强", "首领战上限高", "对厚血怪处理稳定"],
                risks=["没毒时前几回合偏慢", "需要一定防御支撑", "前期太散会容易发虚"],
                next_picks=["Catalyst", "优质防御", "过牌与留牌"],
                pivot_reason="如果后面继续看到毒牌和 Catalyst，这条线会自然长成成熟毒套。",
                source_tags=["Reddit 毒套共识", "中文社区常见路线"],
                source_ids=["steam_silent_style", "reddit_mastering_silent", "reddit_silent_archetypes"],
            ),
            self._build_option(
                key="silent_discard_burst",
                name="静默弃牌爆发",
                score=0.17
                + self._sum_counts(counts, ["Calculated Gamble", "Prepared", "Tactician", "Reflex", "Eviscerate", "Sneaky Strike"]) * 0.2
                + self._sum_counts(counts, ["Acrobatics", "Backflip", "Tools of the Trade"]) * 0.05,
                summary="靠弃牌收益把手牌压缩成高质量爆发回合，成型后节奏和伤害都很凶。",
                core_cards=self._collect_present(counts, ["Calculated Gamble", "Prepared", "Tactician", "Reflex", "Eviscerate", "Sneaky Strike"]),
                support_cards=self._collect_present(counts, ["Acrobatics", "Backflip", "Tools of the Trade", "Dodge and Roll"]),
                missing_pieces=self._missing(["Tactician", "Reflex", "Calculated Gamble"], counts),
                strengths=["回合爆发高", "很容易把手感做顺", "成型后抓牌和出牌效率都强"],
                risks=["收益件不齐时像散牌", "前期容易贪运转忽略保命", "比较吃熟练度"],
                next_picks=["Tactician", "Reflex", "Calculated Gamble", "Tools of the Trade"],
                pivot_reason="如果你已经有杂技、赌博和弃牌收益件，这条线会比普通运转流更值得深走。",
                source_tags=["弃牌爆发", "社区运转流", "高质量回合"],
                source_ids=["silent_discard_burst_route", "reddit_silent_archetypes", "reddit_mastering_silent"],
            ),
            self._build_option(
                key="silent_discard_engine",
                name="静默弃牌引擎",
                score=0.18
                + self._sum_counts(counts, ["Acrobatics", "Calculated Gamble", "Prepared", "Tactician", "Reflex", "Tools of the Trade"]) * 0.17
                + self._sum_counts(counts, ["Backflip", "Dodge and Roll"]) * 0.05,
                summary="靠过牌和弃牌收益把手感做顺，先进入稳定高质量回合，再看要不要转成爆发型弃牌。",
                core_cards=self._collect_present(counts, ["Acrobatics", "Calculated Gamble", "Prepared", "Tactician", "Reflex", "Tools of the Trade"]),
                support_cards=self._collect_present(counts, ["Backflip", "Dodge and Roll", "Sneaky Strike", "Eviscerate"]),
                missing_pieces=self._missing(["Acrobatics", "Calculated Gamble", "稳定防御"], counts),
                strengths=["运转顺", "更容易找关键牌", "中后期提升空间大"],
                risks=["收益件不齐时像散牌过牌", "太偏运转时前期会掉血", "比较怕没有终结手段"],
                next_picks=["高质量防御", "弃牌收益件", "终结手段"],
                pivot_reason="如果你已经有多张过牌牌，这条线最容易自然成型。",
                source_tags=["Reddit 弃牌讨论", "社区运转流"],
                source_ids=["reddit_silent_archetypes", "reddit_learning_silent", "reddit_mastering_silent"],
            ),
            self._build_option(
                key="silent_shiv_tempo",
                name="静默纯刀爆发",
                score=0.18
                + self._sum_counts(counts, ["Blade Dance", "Cloak And Dagger", "Infinite Blades", "Accuracy", "Finisher", "After Image"]) * 0.18
                + self._sum_counts(counts, ["Terror", "Footwork", "Well Laid Plans"]) * 0.05,
                summary="围绕刀和多段伤害打快节奏压制，成型后清杂、爆发和回合密度都很强。",
                core_cards=self._collect_present(counts, ["Blade Dance", "Cloak And Dagger", "Accuracy", "Finisher", "After Image", "Infinite Blades"]),
                support_cards=self._collect_present(counts, ["Terror", "Footwork", "Well Laid Plans", "Backflip"]),
                missing_pieces=self._missing(["Blade Dance", "Accuracy", "After Image"], counts),
                strengths=["前中期清怪快", "低费回合容易打满", "成型后有很强的节奏压制"],
                risks=["缺加成时后期伤害不够", "容易顾打不顾防", "很怕刀件迟迟不来"],
                next_picks=["Blade Dance", "Accuracy", "After Image", "优质防御"],
                pivot_reason="如果奖励和商店频繁给刀流件，这条线会比稳健过渡更值得直接锁定。",
                source_tags=["纯刀", "社区刀流", "多段爆发"],
                source_ids=["silent_pure_shiv_route", "reddit_silent_archetypes", "reddit_mastering_silent"],
            ),
            self._build_option(
                key="silent_dex_shell",
                name="静默敏捷龟甲",
                score=0.15
                + self._sum_counts(counts, ["Footwork", "Blur", "Leg Sweep", "Dodge and Roll", "Backflip", "After Image"]) * 0.16,
                summary="靠敏捷和持续防御把容错做高，再慢慢靠毒、刀或中立输出磨过去。",
                core_cards=self._collect_present(counts, ["Footwork", "Blur", "Leg Sweep", "Dodge and Roll", "After Image"]),
                support_cards=self._collect_present(counts, ["Backflip", "Acrobatics", "Neutralize", "Survivor"]),
                missing_pieces=self._missing(["Footwork", "Blur", "持续输出来源"], counts),
                strengths=["保血能力强", "长战舒服", "很适合稳过渡"],
                risks=["没有输出支点会拖太久", "太慢时会被精英惩罚", "天胡局上限不如毒刀爆发"],
                next_picks=["Footwork", "Leg Sweep", "毒或刀流终结件"],
                pivot_reason="如果现在已经靠防御稳住了，后面可以再决定接毒还是接刀。",
                source_tags=["稳健流", "防御过渡"],
                source_ids=["steam_silent_style", "reddit_learning_silent"],
            ),
            self._build_option(
                key="silent_stable",
                name="静默稳健过渡",
                score=0.21
                + self._sum_counts(counts, ["Dodge and Roll", "Backflip", "Acrobatics", "Leg Sweep", "Quick Slash"]) * 0.09
                + len(snapshot.deck) * 0.004,
                summary="当前更像通用好牌起手，先保住前期节奏，后面再选最顺的主路线。",
                core_cards=self._collect_present(counts, ["Dodge and Roll", "Backflip", "Acrobatics", "Leg Sweep", "Quick Slash"]),
                support_cards=self._collect_present(counts, ["Neutralize", "Survivor", "Strike_G"]),
                missing_pieces=["明确主路线", "更强终结件", "体系核心牌"],
                strengths=["不容易前期暴毙", "转型空间大", "容错高"],
                risks=["中期可能发虚", "上限不够清晰", "太久不定路线会后劲不足"],
                next_picks=["直接变强的牌", "毒或弃牌支点", "别乱拿高费散件"],
                pivot_reason="如果你现在还没成型，这条线最像能把局面稳住的中转站。",
                source_tags=["社区稳健开局", "B站上手思路"],
                source_ids=["bilibili_ai_assistant_demo", "steam_silent_style", "reddit_learning_silent"],
            ),
        ]
        return self._finalize_profile(options, snapshot)

    def _evaluate_defect(self, snapshot: GameSnapshot, counts: dict[str, int]) -> BuildProfile:
        options = [
            self._build_option(
                key="defect_frost_focus",
                name="缺陷冰球聚焦",
                score=0.21
                + self._sum_counts(counts, ["Coolheaded", "Glacier", "Defragment", "Biased Cognition", "Loop", "Capacitor"]) * 0.17,
                summary="靠冰球和聚焦建立稳定防守与持续输出，是机器人最经典也最稳的强势路线之一。",
                core_cards=self._collect_present(counts, ["Coolheaded", "Glacier", "Defragment", "Biased Cognition", "Loop", "Capacitor"]),
                support_cards=self._collect_present(counts, ["Cold Snap", "Charge Battery", "Genetic Algorithm"]),
                missing_pieces=self._missing(["Defragment", "Glacier", "Loop"], counts),
                strengths=["防守稳定", "长战很强", "首领战舒服"],
                risks=["前期没核心时爆发不足", "聚焦太少会发虚", "比较怕前几层纯摸功能件"],
                next_picks=["聚焦来源", "冰球牌", "少量终结件"],
                pivot_reason="如果已经摸到 Glacier 或 Defragment，这条线通常值得优先走。",
                source_tags=["Frost Focus", "经典强线"],
                source_ids=["defect_frost_focus_route", "reddit_defect_archetypes", "reddit_defect_basics"],
            ),
            self._build_option(
                key="defect_power_focus",
                name="缺陷能力聚焦流",
                score=0.16
                + self._sum_counts(counts, ["Defragment", "Biased Cognition", "Capacitor", "Loop", "Echo Form", "Buffer"]) * 0.18
                + self._sum_counts(counts, ["Coolheaded", "Glacier", "Electrodynamics"]) * 0.04,
                summary="用聚焦、能力牌和球槽把每回合质量顶起来，成型后属于很全面的高强度路线。",
                core_cards=self._collect_present(counts, ["Defragment", "Biased Cognition", "Capacitor", "Loop", "Echo Form", "Buffer"]),
                support_cards=self._collect_present(counts, ["Coolheaded", "Glacier", "Electrodynamics"]),
                missing_pieces=self._missing(["Defragment", "Capacitor", "稳定防御"], counts),
                strengths=["中后期压制力强", "攻防都能同步变强", "很适合滚雪球"],
                risks=["能力牌太多时前期会卡", "没底盘时容易贪成长", "成型前不如冰球线稳"],
                next_picks=["Defragment", "Capacitor", "Glacier", "Coolheaded"],
                pivot_reason="如果你已经开始拿聚焦和能力牌，这条线会比普通球体节奏更像版本强线。",
                source_tags=["能力流", "聚焦成长", "版本强线"],
                source_ids=["defect_power_focus_route", "reddit_defect_archetypes"],
            ),
            self._build_option(
                key="defect_dark_orb_burst",
                name="缺陷黑球爆发",
                score=0.16
                + self._sum_counts(counts, ["Darkness", "Recursion", "Loop", "Dualcast", "Multicast"]) * 0.18
                + self._sum_counts(counts, ["Coolheaded", "Defragment"]) * 0.04,
                summary="靠黑球叠大数值后集中引爆，打首领和高血精英时很有威慑力。",
                core_cards=self._collect_present(counts, ["Darkness", "Recursion", "Loop", "Dualcast", "Multicast"]),
                support_cards=self._collect_present(counts, ["Coolheaded", "Defragment", "Charge Battery"]),
                missing_pieces=self._missing(["Darkness", "Recursion", "稳定防守"], counts),
                strengths=["单体爆发高", "打厚血怪强", "路线辨识度高"],
                risks=["成型前回合偏慢", "群怪战不一定舒服", "很看关键牌数量"],
                next_picks=["Darkness", "Recursion", "防御底盘"],
                pivot_reason="如果你已经有黑球相关组件，这条线会比纯球体节奏更有终局感。",
                source_tags=["Dark Orb", "黑球爆发"],
                source_ids=["defect_dark_orb_route", "reddit_defect_archetypes"],
            ),
            self._build_option(
                key="defect_zero_cost_loop",
                name="缺陷零费爪循环",
                score=0.15
                + self._sum_counts(counts, ["Claw", "Beam Cell", "Go for the Eyes", "Steam Barrier", "FTL", "All For One", "Scrape"]) * 0.16,
                summary="靠零费牌、爪和回收件堆高回合频率，成型后操作感和爆发都非常足。",
                core_cards=self._collect_present(counts, ["Claw", "All For One", "Beam Cell", "FTL", "Steam Barrier", "Scrape"]),
                support_cards=self._collect_present(counts, ["Go for the Eyes", "Hologram", "Skim", "Compile Driver"]),
                missing_pieces=self._missing(["Claw", "All For One", "稳定过牌"], counts),
                strengths=["回合操作感强", "低费不卡手", "成型后爆发和节奏都不错"],
                risks=["没回收件时容易散", "很吃组件密度", "过渡期可能两头不到岸"],
                next_picks=["Claw", "All For One", "Skim", "Hologram"],
                pivot_reason="如果你已经开始拿到多张零费牌或爪，这条线就值得重点留意。",
                source_tags=["零费循环", "Claw", "高操作路线"],
                source_ids=["defect_zero_cost_claw_route", "reddit_defect_archetypes", "reddit_defect_basics"],
            ),
            self._build_option(
                key="defect_orb_tempo",
                name="缺陷球体节奏",
                score=0.19
                + self._sum_counts(counts, ["Ball Lightning", "Zap", "Dualcast", "Electrodynamics", "Cold Snap", "Loop"]) * 0.14,
                summary="靠电球和轮转先把前中期节奏撑住，再看后面补聚焦还是补终结。",
                core_cards=self._collect_present(counts, ["Ball Lightning", "Zap", "Dualcast", "Electrodynamics", "Cold Snap"]),
                support_cards=self._collect_present(counts, ["Beam Cell", "Coolheaded", "Charge Battery"]),
                missing_pieces=self._missing(["聚焦来源", "更强防守", "稳定抽牌"], counts),
                strengths=["前中期顺", "群怪战舒服", "转型空间还在"],
                risks=["后期没聚焦会疲软", "怕防御不足掉血", "路线容易停在半成型"],
                next_picks=["聚焦", "冰球", "抽牌与能量"],
                pivot_reason="如果你是靠球体本身在打节奏，这条线最自然。",
                source_tags=["球体节奏", "稳健过渡"],
                source_ids=["reddit_defect_basics", "reddit_defect_archetypes"],
            ),
            self._build_option(
                key="defect_stable",
                name="缺陷稳健过渡",
                score=0.21
                + self._sum_counts(counts, ["Coolheaded", "Charge Battery", "Genetic Algorithm", "Cold Snap"]) * 0.09,
                summary="当前更像以通用优质球体牌维持强度，后面再决定往哪条成型线深走。",
                core_cards=self._collect_present(counts, ["Coolheaded", "Charge Battery", "Genetic Algorithm", "Cold Snap"]),
                support_cards=self._collect_present(counts, ["Zap", "Dualcast", "Defend_B"]),
                missing_pieces=["聚焦来源", "终局方向", "更强球体支撑"],
                strengths=["转型空间大", "前期稳", "后续奖励好接"],
                risks=["路线不清晰", "一直过渡会中期疲软", "爆发上限暂时不足"],
                next_picks=["直接变强的球体牌", "聚焦", "少拿高费虚牌"],
                pivot_reason="如果当前只是靠好牌支撑局面，这条线最像安全中转站。",
                source_tags=["机器人稳开", "新手友好"],
                source_ids=["reddit_defect_basics"],
            ),
        ]
        return self._finalize_profile(options, snapshot)

    def _evaluate_ironclad(self, snapshot: GameSnapshot, counts: dict[str, int]) -> BuildProfile:
        options = [
            self._build_option(
                key="ironclad_exhaust_engine",
                name="铁甲腐化废牌",
                score=0.19
                + self._sum_counts(counts, ["Feel No Pain", "True Grit", "Burning Pact", "Fiend Fire", "Dark Embrace", "Second Wind", "Corruption"]) * 0.18,
                summary="围绕腐化、拥抱和无痛把废牌变成资源，越打越顺，是铁甲最强也最有代表性的路线之一。",
                core_cards=self._collect_present(counts, ["Corruption", "Dark Embrace", "Feel No Pain", "True Grit", "Burning Pact", "Fiend Fire"]),
                support_cards=self._collect_present(counts, ["ShrugItOff", "Power Through", "Second Wind", "Offering"]),
                missing_pieces=self._missing(["Corruption", "Dark Embrace", "Feel No Pain"], counts),
                strengths=["资源转化强", "能快速清废牌", "中后期上限高"],
                risks=["缺关键件时像拼图", "前期贪联动会影响稳定", "比较吃抓牌顺序"],
                next_picks=["Corruption", "Dark Embrace", "Feel No Pain", "Second Wind"],
                pivot_reason="如果你已经拿到真格挡、燃烧契约或无痛，这条线会越来越像真正的腐化废牌。",
                source_tags=["腐化废牌", "Exhaust", "版本强线"],
                source_ids=["ironclad_corruption_exhaust_route", "reddit_ironclad_archetypes"],
            ),
            self._build_option(
                key="ironclad_barricade_block",
                name="铁甲 Body Slam 叠甲",
                score=0.16
                + self._sum_counts(counts, ["Barricade", "Entrench", "Body Slam", "Impervious", "ShrugItOff", "Flame Barrier"]) * 0.17,
                summary="靠叠甲、倍甲和 Body Slam 把防御直接转成击杀，成型后很多战斗都像开了保险。",
                core_cards=self._collect_present(counts, ["Barricade", "Entrench", "Body Slam", "Impervious", "Juggernaut"]),
                support_cards=self._collect_present(counts, ["ShrugItOff", "Flame Barrier", "Power Through", "Second Wind"]),
                missing_pieces=self._missing(["Body Slam", "Barricade", "Entrench"], counts),
                strengths=["容错很高", "长战稳", "打物理怪特别舒服"],
                risks=["前期没组件会太慢", "没倍甲时终结速度一般", "怕成型前被直接压死"],
                next_picks=["Body Slam", "Barricade", "Entrench", "优质格挡"],
                pivot_reason="如果已经见到 Barricade 或 Body Slam，这条线就值得列入高优先级备选。",
                source_tags=["Body Slam", "叠甲", "厚重防守"],
                source_ids=["ironclad_body_slam_block_route", "reddit_ironclad_archetypes"],
            ),
            self._build_option(
                key="ironclad_strength_burst",
                name="铁甲力量爆发",
                score=0.18
                + self._sum_counts(counts, ["Inflame", "Spot Weakness", "Limit Break", "Demon Form", "Heavy Blade", "Sword Boomerang", "Reaper"]) * 0.16,
                summary="先活住，再把力量做高，后续单体和收割上限都非常夸张。",
                core_cards=self._collect_present(counts, ["Inflame", "Spot Weakness", "Limit Break", "Demon Form", "Heavy Blade", "Sword Boomerang"]),
                support_cards=self._collect_present(counts, ["ShrugItOff", "PommelStrike", "Offering", "Reaper"]),
                missing_pieces=self._missing(["稳定防御", "力量兑现件", "更顺过牌"], counts),
                strengths=["首领战强", "单体上限高", "成长方向明确"],
                risks=["成型前偏慢", "防御差会来不及成长", "很看兑现件有没有跟上"],
                next_picks=["Shrug It Off", "力量牌", "高质量过牌"],
                pivot_reason="如果力量牌已经出现两张以上，基本就能开始往这条线靠。",
                source_tags=["力量爆发", "经典铁甲路线"],
                source_ids=["ironclad_strength_burst_route", "reddit_ironclad_archetypes"],
            ),
            self._build_option(
                key="ironclad_wound_synergy",
                name="铁甲伤口状态联动",
                score=0.14
                + self._sum_counts(counts, ["Power Through", "Evolve", "Fire Breathing", "Second Wind", "Feel No Pain"]) * 0.16,
                summary="把伤口和状态牌从副作用变成收益，属于成型后很舒服的偏门强势线。",
                core_cards=self._collect_present(counts, ["Power Through", "Evolve", "Fire Breathing", "Second Wind", "Feel No Pain"]),
                support_cards=self._collect_present(counts, ["True Grit", "Burning Pact", "ShrugItOff"]),
                missing_pieces=self._missing(["Evolve", "Feel No Pain", "状态联动件"], counts),
                strengths=["对状态牌容忍度高", "某些战斗特别爽", "路线特色明显"],
                risks=["组件不齐时偏笨重", "容易卡手", "终结速度不如力量或废牌"],
                next_picks=["Evolve", "Feel No Pain", "Fire Breathing"],
                pivot_reason="如果你已经开始有伤口和状态联动件，这条线可以当作强备选。",
                source_tags=["伤口流", "状态联动"],
                source_ids=["reddit_ironclad_archetypes"],
            ),
            self._build_option(
                key="ironclad_stable",
                name="铁甲前期战力过渡",
                score=0.22
                + self._sum_counts(counts, ["PommelStrike", "ShrugItOff", "Bash", "Anger"]) * 0.09,
                summary="当前更像靠优质即战力过第一幕，后面再看最顺的成长路线。",
                core_cards=self._collect_present(counts, ["PommelStrike", "ShrugItOff", "Bash", "Anger"]),
                support_cards=self._collect_present(counts, ["Strike_R", "Defend_R", "Inflame"]),
                missing_pieces=["明确成长方向", "更强核心牌", "更顺运转"],
                strengths=["即时战力不错", "前期容错高", "后续还能转型"],
                risks=["中期会发虚", "容易拿太多普通输出", "不及时定线会后劲不足"],
                next_picks=["过牌", "防御", "路线核心牌"],
                pivot_reason="如果你还没定型，先走稳健过渡最不容易翻车。",
                source_tags=["铁甲稳健开局", "社区通用建议"],
                source_ids=["reddit_ironclad_archetypes"],
            ),
        ]
        return self._finalize_profile(options, snapshot)

    def _evaluate_watcher(self, snapshot: GameSnapshot, counts: dict[str, int]) -> BuildProfile:
        options = [
            self._build_option(
                key="watcher_stance_burst",
                name="观者姿态爆发",
                score=0.22
                + self._sum_counts(counts, ["Eruption", "Vigilance", "Tantrum", "Inner Peace", "Fear No Evil", "Rushdown", "Talk to the Hand"]) * 0.16,
                summary="靠进怒爆发、退怒保命打高质量回合，是观者最经典也最强的主流路线。",
                core_cards=self._collect_present(counts, ["Eruption", "Vigilance", "Tantrum", "Inner Peace", "Fear No Evil", "Rushdown", "Talk to the Hand"]),
                support_cards=self._collect_present(counts, ["Flurry Of Blows", "Mental Fortress", "Empty Mind"]),
                missing_pieces=self._missing(["稳定退怒", "Rushdown", "保命件"], counts),
                strengths=["爆发高", "回合上限高", "成型后压制力强"],
                risks=["切姿态失误掉血多", "退不出来会很危险", "很吃操作顺序"],
                next_picks=["退怒件", "Rushdown", "保命与抽牌"],
                pivot_reason="如果已经有 Tantrum、Rushdown 这类牌，这条线优先级很高。",
                source_tags=["姿态爆发", "Rushdown", "观者主流"],
                source_ids=["watcher_rushdown_combo_route", "reddit_watcher_archetypes", "reddit_watcher_basics"],
            ),
            self._build_option(
                key="watcher_rushdown_combo",
                name="观者 Rushdown 连段",
                score=0.18
                + self._sum_counts(counts, ["Rushdown", "Tantrum", "Inner Peace", "Fear No Evil", "Empty Mind", "Scrawl"]) * 0.18,
                summary="围绕 Rushdown 和姿态来回切换做连段，属于观者最典型的高上限路线。",
                core_cards=self._collect_present(counts, ["Rushdown", "Tantrum", "Inner Peace", "Fear No Evil", "Empty Mind", "Scrawl"]),
                support_cards=self._collect_present(counts, ["Vigilance", "Eruption", "Talk to the Hand"]),
                missing_pieces=self._missing(["Rushdown", "稳定退怒", "抽牌补充"], counts),
                strengths=["爆发极高", "有机会形成半无限", "成型后非常离谱"],
                risks=["组件要求高", "没抽到核心时手感一般", "需要一定熟练度"],
                next_picks=["Rushdown", "Tantrum", "Empty Mind", "Scrawl"],
                pivot_reason="如果已经有 Rushdown 支点，这条线会比普通姿态流更值得深走。",
                source_tags=["Rushdown 连段", "高上限"],
                source_ids=["watcher_rushdown_combo_route", "reddit_watcher_archetypes"],
            ),
            self._build_option(
                key="watcher_scry_control",
                name="观者占卜控制",
                score=0.16
                + self._sum_counts(counts, ["Third Eye", "Cut Through Fate", "Just Lucky", "Weave", "Nirvana", "Evaluate"]) * 0.16,
                summary="靠占卜优化抽牌和回合质量，再配合姿态或低费连段打节奏。",
                core_cards=self._collect_present(counts, ["Third Eye", "Cut Through Fate", "Just Lucky", "Weave", "Nirvana"]),
                support_cards=self._collect_present(counts, ["Inner Peace", "Fear No Evil", "Flurry Of Blows"]),
                missing_pieces=self._missing(["Third Eye", "Cut Through Fate", "更多占卜收益"], counts),
                strengths=["手感顺", "更容易找到关键牌", "攻防两端都能受益"],
                risks=["缺收益件时只是修牌", "纯爆发不如姿态流", "需要后续牌组配合"],
                next_picks=["占卜收益件", "姿态联动", "低费高质量牌"],
                pivot_reason="如果你已经拿到几张占卜牌，这条线会比硬走纯姿态更顺手。",
                source_tags=["占卜控制", "稳健观者"],
                source_ids=["watcher_scry_control_route", "reddit_watcher_archetypes"],
            ),
            self._build_option(
                key="watcher_divinity_burst",
                name="观者天人爆发",
                score=0.14
                + self._sum_counts(counts, ["Devotion", "Worship", "Prostrate", "Pray", "Blasphemy", "Deus Ex Machina"]) * 0.18
                + self._sum_counts(counts, ["Cut Through Fate", "Third Eye"]) * 0.04,
                summary="围绕神格和一次性爆发做大回合，胡起来上限很高，但也更吃组件。",
                core_cards=self._collect_present(counts, ["Devotion", "Worship", "Prostrate", "Pray", "Blasphemy", "Deus Ex Machina"]),
                support_cards=self._collect_present(counts, ["Cut Through Fate", "Third Eye", "Scrawl"]),
                missing_pieces=self._missing(["Devotion", "Worship", "稳定防守"], counts),
                strengths=["单回合爆发夸张", "打部分首领会很爽", "路线辨识度高"],
                risks=["组件要求高", "没天人前过渡偏弱", "比姿态线更容易发牌序问题"],
                next_picks=["Devotion", "Worship", "Scrawl", "保命件"],
                pivot_reason="如果你已经摸到神格组件，这条线可以作为更贪上限的强备选。",
                source_tags=["天人", "神格爆发", "高上限"],
                source_ids=["watcher_divinity_burst_route", "reddit_watcher_archetypes"],
            ),
            self._build_option(
                key="watcher_pressure_points",
                name="观者印记特化",
                score=0.12
                + self._sum_counts(counts, ["Pressure Points", "Third Eye", "Evaluate", "Sanctity"]) * 0.17,
                summary="比较吃组件的偏门路线，成型后打高格挡敌人会很舒服。",
                core_cards=self._collect_present(counts, ["Pressure Points", "Third Eye", "Evaluate", "Sanctity"]),
                support_cards=self._collect_present(counts, ["Inner Peace", "Vigilance"]),
                missing_pieces=self._missing(["Pressure Points", "更多印记件", "稳定防守"], counts),
                strengths=["不吃普通攻击倍率", "路线辨识度高", "打特定敌人很强"],
                risks=["没摸到组件时很弱", "容易被散牌拖慢", "不建议无脑硬转"],
                next_picks=["Pressure Points", "防御", "少拿无关攻击"],
                pivot_reason="这条线只建议在已经拿到印记牌时当作候选，不建议硬转。",
                source_tags=["印记流", "偏门路线"],
                source_ids=["reddit_watcher_archetypes", "reddit_watcher_basics"],
            ),
            self._build_option(
                key="watcher_stable",
                name="观者稳健过渡",
                score=0.22
                + self._sum_counts(counts, ["Eruption", "Vigilance", "Inner Peace", "Third Eye"]) * 0.09,
                summary="当前更像靠姿态基本功和通用好牌维持强度，后面再选最顺的成型线。",
                core_cards=self._collect_present(counts, ["Eruption", "Vigilance", "Inner Peace", "Third Eye"]),
                support_cards=self._collect_present(counts, ["Strike_P", "Defend_P", "Fear No Evil"]),
                missing_pieces=["更顺的姿态循环", "稳定抽牌", "明确终结件"],
                strengths=["调整空间大", "前期稳住就不差", "后续奖励很好修正"],
                risks=["路线不够明确", "一直拿散件会很平", "上限要靠后面补件"],
                next_picks=["姿态稳定件", "抽牌", "高质量输出"],
                pivot_reason="如果还没看到强关键牌，先走稳健过渡最安全。",
                source_tags=["观者稳健开局", "新手友好"],
                source_ids=["reddit_watcher_basics"],
            ),
        ]
        return self._finalize_profile(options, snapshot)

    def _build_option(
        self,
        key: str,
        name: str,
        score: float,
        summary: str,
        core_cards: list[str],
        support_cards: list[str],
        missing_pieces: list[str],
        strengths: list[str],
        risks: list[str],
        next_picks: list[str],
        pivot_reason: str,
        source_tags: list[str] | None = None,
        source_ids: list[str] | None = None,
    ) -> BuildOption:
        normalized_score = max(0.05, min(score, 0.98))
        resolved_source_ids = list(dict.fromkeys((source_ids or []) + self._source_ids_from_tags(source_tags or [])))
        community_sources = self.community.sources_for_ids(resolved_source_ids[:3])
        return BuildOption(
            key=key,
            name=name,
            rating=self._rating_from_score(normalized_score),
            tier_label=self._tier_label_from_score(normalized_score),
            score=normalized_score,
            summary=summary,
            core_cards=[self._display_label(item) for item in core_cards[:6]],
            support_cards=[self._display_label(item) for item in support_cards[:6]],
            missing_pieces=[self._display_label(item) for item in missing_pieces[:5]],
            strengths=strengths[:4],
            risks=risks[:4],
            next_picks=[self._display_label(item) for item in next_picks[:5]],
            pivot_reason=pivot_reason,
            source_tags=list(source_tags or []),
            source_ids=resolved_source_ids[:5],
            community_summary=self._community_summary_for_sources(community_sources),
            community_sources=community_sources,
        )

    def _finalize_profile(self, options: list[BuildOption], snapshot: GameSnapshot) -> BuildProfile:
        ordered = sorted(
            options,
            key=lambda item: (self._rating_priority(item.rating), item.score),
            reverse=True,
        )
        primary = ordered[0]
        primary.recommended_now = True

        alternatives = [item for item in ordered[1:] if item.rating in {"S", "A"}][:4]
        if len(alternatives) < 4:
            seen = {item.key for item in alternatives}
            for item in ordered[1:]:
                if item.key in seen:
                    continue
                alternatives.append(item)
                seen.add(item.key)
                if len(alternatives) >= 4:
                    break

        general_note = self.community.general_note(snapshot.character_class, snapshot.floor or 0)
        source_tags = list(primary.source_tags)
        source_ids = list(primary.source_ids)
        if general_note is not None:
            for hint in general_note.archetype_hints[:3]:
                if hint not in source_tags:
                    source_tags.append(hint)
            source_ids.extend(list(general_note.source_ids))

        deduped_source_ids = list(dict.fromkeys(source_ids))[:3]
        community_sources = self.community.sources_for_ids(deduped_source_ids)

        return BuildProfile(
            name=primary.name,
            rating=primary.rating,
            tier_label=primary.tier_label,
            score=primary.score,
            summary=primary.summary,
            core_cards=primary.core_cards,
            support_cards=primary.support_cards,
            missing_pieces=primary.missing_pieces,
            strengths=primary.strengths,
            risks=primary.risks,
            next_picks=primary.next_picks,
            archetype_key=primary.key,
            source_tags=source_tags[:5],
            source_ids=deduped_source_ids,
            community_summary=primary.community_summary or self._community_summary_for_sources(community_sources),
            community_sources=community_sources,
            alternatives=alternatives,
            route_stage=self._route_stage(snapshot),
            two_fight_goal=self._two_fight_goal(primary),
            pivot_triggers=self._pivot_triggers(primary),
            avoid_now=self._avoid_now(primary),
        )

    def _rating_from_score(self, score: float) -> str:
        if score >= 0.9:
            return "S"
        if score >= 0.8:
            return "A"
        if score >= 0.7:
            return "B"
        if score >= 0.6:
            return "C"
        return "D"

    def _tier_label_from_score(self, score: float) -> str:
        rating = self._rating_from_score(score)
        mapping = {
            "S": "当前版本强势主构筑",
            "A": "稳定强线",
            "B": "可走但更看组件",
            "C": "偏过渡或备选",
            "D": "暂时不建议主走",
        }
        return mapping.get(rating, "待评估")

    def _rating_priority(self, rating: str) -> int:
        return {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}.get(rating.upper(), 0)

    def _source_ids_from_tags(self, source_tags: list[str]) -> list[str]:
        normalized = " ".join(source_tags).casefold()
        candidates: list[str] = []
        for source_id, source in self.community.sources.items():
            haystack = " ".join([source.title, source.publisher, *source.tags]).casefold()
            if normalized and any(tag.casefold() in haystack or tag.casefold() in normalized for tag in source_tags):
                candidates.append(source_id)
        return list(dict.fromkeys(candidates))

    def _community_summary_for_sources(self, sources: list[dict[str, str]]) -> str | None:
        for source in sources:
            summary = (source.get("summary") or "").strip()
            if summary:
                return summary
        return None

    def _deck_counts(self, snapshot: GameSnapshot) -> dict[str, int]:
        counts: dict[str, int] = {}
        for card in snapshot.deck:
            counts[card.id] = counts.get(card.id, 0) + 1
        return counts

    def _sum_counts(self, counts: dict[str, int], card_ids: list[str]) -> int:
        return sum(counts.get(card_id, 0) for card_id in card_ids)

    def _collect_present(self, counts: dict[str, int], card_ids: list[str]) -> list[str]:
        return [card_id for card_id in card_ids if counts.get(card_id, 0) > 0]

    def _missing(self, wanted: list[str], counts: dict[str, int]) -> list[str]:
        missing: list[str] = []
        for card_id in wanted:
            if any("\u4e00" <= ch <= "\u9fff" for ch in card_id):
                missing.append(card_id)
                continue
            if counts.get(card_id, 0) <= 0:
                missing.append(card_id)
        return missing

    def _display_label(self, value: str) -> str:
        if not value:
            return value
        if any("\u4e00" <= ch <= "\u9fff" for ch in value):
            return value
        return resolve_card_name(value, None)

    def _evaluate_generic(self, snapshot: GameSnapshot) -> BuildProfile:
        deck_size = len(snapshot.deck)
        note = self.community.general_note(snapshot.character_class, snapshot.floor or 0)
        score = 0.55 + min(deck_size, 20) * 0.01
        summary = "这套牌目前还在过渡期，建议先围绕当前最稳定的强度来源继续补强。"
        source_tags = ["本地规则"]
        source_ids: list[str] = []
        if note is not None:
            source_ids = list(note.source_ids[:3])
            if note.reason_lines:
                summary = note.reason_lines[0]
            if note.archetype_hints:
                source_tags = ["社区通用建议", *list(note.archetype_hints[:2])]

        community_sources = self.community.sources_for_ids(source_ids)
        return BuildProfile(
            name="当前构筑过渡中",
            rating=self._rating_from_score(score),
            tier_label=self._tier_label_from_score(score),
            score=score,
            summary=summary,
            core_cards=[],
            support_cards=[],
            missing_pieces=["更明确的主路线", "更高质量的核心牌"],
            strengths=["还有调整空间"],
            risks=["如果一直不定路线，中期容易乏力"],
            next_picks=["优先拿能直接变强的牌", "避免无关散件越拿越厚"],
            archetype_key="generic",
            source_tags=source_tags,
            source_ids=source_ids,
            community_summary=self._community_summary_for_sources(community_sources) or (None if note is None else note.build_direction),
            community_sources=community_sources,
            alternatives=[],
            route_stage=self._route_stage(snapshot),
            two_fight_goal=["先补能立刻变强的牌", "两场内尽量确认主路线"],
            pivot_triggers=["拿到明显核心牌时再锁路线", "商店见到强联动件再转型"],
            avoid_now=["少拿高费散件", "别让套牌又厚又没方向"],
        )

    def _route_stage(self, snapshot: GameSnapshot) -> str:
        floor = snapshot.floor or 0
        if floor <= 6:
            return "开局定底盘"
        if floor <= 17:
            return "第一幕中段补路线"
        if floor <= 34:
            return "中局锁主线"
        return "后期补终局"

    def _two_fight_goal(self, profile: BuildProfile) -> list[str]:
        goals = [item for item in profile.next_picks[:2] if item]
        if len(goals) < 2:
            goals.extend(item for item in profile.missing_pieces[: 2 - len(goals)] if item)
        return goals[:2]

    def _pivot_triggers(self, profile: BuildOption) -> list[str]:
        hints: list[str] = []
        if profile.pivot_reason:
            hints.append(profile.pivot_reason)
        if profile.missing_pieces:
            hints.append(f"一旦补到“{profile.missing_pieces[0]}”，这条线会更像成型构筑。")
        return hints[:2]

    def _avoid_now(self, profile: BuildOption) -> list[str]:
        avoids: list[str] = []
        if profile.risks:
            avoids.append(profile.risks[0])
        if profile.missing_pieces:
            avoids.append(f"在补到“{profile.missing_pieces[0]}”前，先别为了想象上限硬贪散件。")
        return avoids[:2]
