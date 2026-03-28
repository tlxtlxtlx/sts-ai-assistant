from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sts_ai_assistant.llm.base import AssistantReply, ChatTurn, RecommendationResult
from sts_ai_assistant.parsing.display_names import (
    resolve_card_name,
    resolve_potion_name,
    resolve_relic_name,
)
from sts_ai_assistant.parsing.models import CardSnapshot, GameSnapshot
from sts_ai_assistant.service.build_profile import BuildProfile, BuildProfileEvaluator
from sts_ai_assistant.service.community_knowledge import CommunityKnowledgeBase


@dataclass(slots=True)
class _RewardEvaluation:
    card: CardSnapshot
    score: float
    reasons: list[str]
    build_direction: str
    fit_score: float = 0.0
    fit_label: str = ""
    route_after_pick: str = ""
    route_family: str = ""


@dataclass(slots=True)
class _CombatCard:
    id: str
    name: str
    cost: int | None
    type: str | None
    playable: bool


@dataclass(slots=True)
class RuleBasedAdvisor:
    community: CommunityKnowledgeBase = field(init=False)
    build_profiles: BuildProfileEvaluator = field(init=False)

    def __post_init__(self) -> None:
        self.community = CommunityKnowledgeBase()
        self.build_profiles = BuildProfileEvaluator()

    def recommend(self, snapshot: GameSnapshot) -> RecommendationResult | None:
        screen_type = snapshot.context.screen_type.upper()
        if screen_type == "CARD_REWARD":
            return self._recommend_card_reward(snapshot)
        if screen_type in {"SHOP", "SHOP_SCREEN"}:
            return self._recommend_shop(snapshot)
        if screen_type in {"BOSS_REWARD", "COMBAT_REWARD", "TREASURE", "CHEST"}:
            return self._recommend_relic_reward(snapshot)
        if screen_type == "COMBAT":
            return self._recommend_combat(snapshot)
        return None

    def analyze(
        self,
        snapshot: GameSnapshot,
        source: str,
        focus: str | None = None,
    ) -> AssistantReply | None:
        del focus
        recommendation = self.recommend(snapshot)
        if recommendation is None:
            return None
        return self._reply_from_recommendation(recommendation, source=source)

    def chat(
        self,
        snapshot: GameSnapshot,
        source: str,
        message: str,
        history: list[ChatTurn] | None = None,
    ) -> AssistantReply | None:
        del history
        lowered = message.casefold()
        screen_type = snapshot.context.screen_type.upper()
        reward_keywords = ("拿哪", "选哪", "跳过", "reward", "take", "skip", "bowl")
        relic_keywords = ("遗物", "relic", "boss relic", "蓝钥匙", "宝箱", "sapphire key")
        shop_keywords = ("商店", "删牌", "删除", "移除", "purge", "remove", "shop", "该买吗", "买哪", "值得买吗")
        combat_keywords = ("出哪", "先出", "怎么打", "顺序", "play", "combat", "回合")

        if "缺什么" in lowered or "缺啥" in lowered or "缺哪块" in lowered:
            return self._reply_for_build_gap(snapshot, source=source)

        if (
            "为什么不删牌" in lowered
            or ("删牌" in lowered and "为什么" in lowered)
            or ("推荐删牌" in lowered and "为什么" in lowered)
        ):
            return self._reply_for_remove_timing(snapshot, source=source)

        if ("接下来" in lowered and ("找什么" in lowered or "该找" in lowered)) or (
            "两场" in lowered and ("找什么" in lowered or "该找" in lowered)
        ):
            return self._reply_for_next_picks(snapshot, source=source)

        if screen_type == "CARD_REWARD" or any(keyword in lowered for keyword in reward_keywords):
            reply = self.analyze(snapshot, source=source)
            if reply is not None:
                return reply

        if screen_type in {"SHOP", "SHOP_SCREEN"} or any(keyword in lowered for keyword in shop_keywords):
            recommendation = self._recommend_shop(snapshot)
            if recommendation is not None:
                return self._reply_from_recommendation(recommendation, source=source)

        if screen_type in {"BOSS_REWARD", "COMBAT_REWARD", "TREASURE", "CHEST"} or any(
            keyword in lowered for keyword in relic_keywords
        ):
            recommendation = self._recommend_relic_reward(snapshot)
            if recommendation is not None:
                return self._reply_from_recommendation(recommendation, source=source)

        if screen_type == "COMBAT" or any(keyword in lowered for keyword in combat_keywords):
            recommendation = self._recommend_combat(snapshot)
            if recommendation is not None:
                return self._reply_from_recommendation(recommendation, source=source)

        return None

    def _reply_for_build_gap(self, snapshot: GameSnapshot, source: str) -> AssistantReply:
        profile = self.build_profiles.evaluate(snapshot)
        recommendation = self.recommend(snapshot)
        raw = recommendation.raw_response if recommendation is not None else {}
        fills_gap = self._as_text(raw.get("fills_gap")) if raw else None
        gap_label = self._gap_label(profile, fills_gap)
        next_targets = profile.two_fight_goal[:2] or profile.next_picks[:2] or profile.missing_pieces[:2]

        reasons: list[str] = []
        if fills_gap:
            reasons.append(fills_gap)
        else:
            reasons.append(f"你当前更像“{profile.name}”，还缺一块能让回合更稳的直接补强。")
        if recommendation is not None and recommendation.primary_target:
            reasons.append(f"这也是为什么当前更推荐优先处理“{recommendation.primary_target}”。")
        if next_targets:
            reasons.append(f"接下来两场优先找“{' / '.join(next_targets)}”，先把这块补完整。")
        if profile.risks:
            reasons.append(f"如果一直不补，最容易出现的问题是：{profile.risks[0]}。")

        alternatives = recommendation.alternatives[:2] if recommendation is not None else []
        if next_targets:
            alternatives = list(dict.fromkeys([*alternatives, *next_targets[:1]]))[:3]

        return AssistantReply(
            mode="chat",
            source=source,
            conclusion=f"当前这套牌最缺{gap_label}。",
            reasons=self._dedupe_lines(reasons)[:4],
            alternatives=alternatives,
            build_direction=(recommendation.build_direction if recommendation and recommendation.build_direction else profile.route_stage or profile.name),
            raw_response={
                "rule_based": True,
                "question_type": "build_gap",
                "build_profile": profile.to_dict(),
                "recommendation": recommendation.to_dict() if recommendation is not None else None,
            },
        )

    def _reply_for_remove_timing(self, snapshot: GameSnapshot, source: str) -> AssistantReply:
        profile = self.build_profiles.evaluate(snapshot)
        recommendation = self.recommend(snapshot)
        remove_target = self._best_remove_target(snapshot)
        screen_type = snapshot.context.screen_type.upper()

        if screen_type in {"SHOP", "SHOP_SCREEN"}:
            shop_recommendation = self._recommend_shop(snapshot)
            if shop_recommendation is not None and shop_recommendation.suggested_action.upper() == "REMOVE":
                target = shop_recommendation.primary_target or remove_target
                reasons = [line.strip() for line in shop_recommendation.reasoning.splitlines() if line.strip()]
                if target:
                    reasons.append(f"删掉“{target}”以后，后面更容易抽到你真正想要的牌。")
                if profile.next_picks:
                    reasons.append(f"删完以后，接下来还是优先补“{' / '.join(profile.next_picks[:2])}”。")
                return AssistantReply(
                    mode="chat",
                    source=source,
                    conclusion=f"这家商店更推荐先删“{target}”。" if target else "这家商店更推荐先删牌。",
                    reasons=self._dedupe_lines(reasons)[:4],
                    alternatives=shop_recommendation.alternatives[:3],
                    build_direction=shop_recommendation.build_direction,
                    raw_response={
                        "rule_based": True,
                        "question_type": "remove_timing",
                        "recommendation": shop_recommendation.to_dict(),
                    },
                )

            reasons = ["这家商店当前更值的是先处理能立刻提升强度的项目，删牌优先级没那么高。"]
            if shop_recommendation is not None and shop_recommendation.primary_target:
                reasons.append(f"和删牌相比，这次更赚的是先拿“{shop_recommendation.primary_target}”。")
            if remove_target:
                reasons.append(f"如果后面还有机会进商店，再考虑删“{remove_target}”。")
            if profile.risks:
                reasons.append(f"你当前更需要先解决的是：{profile.risks[0]}。")
            return AssistantReply(
                mode="chat",
                source=source,
                conclusion="这家商店现在先不急着删牌。",
                reasons=self._dedupe_lines(reasons)[:4],
                alternatives=[item for item in [remove_target, *(profile.next_picks[:2])] if item][:3],
                build_direction=(shop_recommendation.build_direction if shop_recommendation is not None else profile.route_stage or profile.name),
                raw_response={
                    "rule_based": True,
                    "question_type": "remove_timing",
                    "recommendation": shop_recommendation.to_dict() if shop_recommendation is not None else None,
                },
            )

        reasons = ["当前不是商店节点，删牌这件事要等到商店才能真正执行。"]
        if recommendation is not None and recommendation.primary_target:
            reasons.append(f"这层更该先处理“{recommendation.primary_target}”这种能立刻变强的选择。")
        if remove_target:
            reasons.append(f"等后面进商店时，再优先考虑删“{remove_target}”。")
        if (snapshot.floor or 0) <= 6:
            reasons.append("第一幕前几层通常先保血和补直接战力，比提前纠结删牌更重要。")
        elif profile.next_picks:
            reasons.append(f"你现在更该先补“{' / '.join(profile.next_picks[:2])}”。")

        return AssistantReply(
            mode="chat",
            source=source,
            conclusion="现在先不急着删牌。",
            reasons=self._dedupe_lines(reasons)[:4],
            alternatives=[item for item in [remove_target, *(profile.next_picks[:2])] if item][:3],
            build_direction=(recommendation.build_direction if recommendation and recommendation.build_direction else profile.route_stage or profile.name),
            raw_response={
                "rule_based": True,
                "question_type": "remove_timing",
                "recommendation": recommendation.to_dict() if recommendation is not None else None,
            },
        )

    def _reply_for_next_picks(self, snapshot: GameSnapshot, source: str) -> AssistantReply:
        profile = self.build_profiles.evaluate(snapshot)
        recommendation = self.recommend(snapshot)
        goals = profile.two_fight_goal[:2] or profile.next_picks[:2] or profile.missing_pieces[:2]
        goal_text = " / ".join(goals) if goals else "直接变强的牌"

        reasons = [f"你当前更像“{profile.name}”，先把这块补齐，后面更容易定主路线。"]
        if profile.route_stage:
            reasons.append(f"这局现在先学的是：{profile.route_stage}。")
        if recommendation is not None and recommendation.primary_target:
            reasons.append(f"眼前这一步如果能拿到“{recommendation.primary_target}”，也算是在往这条线补。")
        if profile.avoid_now:
            reasons.append(f"现在先别急着碰：{profile.avoid_now[0]}。")

        return AssistantReply(
            mode="chat",
            source=source,
            conclusion=f"接下来两场优先找“{goal_text}”。",
            reasons=self._dedupe_lines(reasons)[:4],
            alternatives=goals[:3],
            build_direction=(recommendation.build_direction if recommendation and recommendation.build_direction else profile.route_stage or profile.name),
            raw_response={
                "rule_based": True,
                "question_type": "next_picks",
                "build_profile": profile.to_dict(),
                "recommendation": recommendation.to_dict() if recommendation is not None else None,
            },
        )

    def _gap_label(self, profile: BuildProfile, fills_gap: str | None) -> str:
        text = fills_gap or ""
        if "防守" in text or "稳定" in text or "掉血" in text:
            return "防守和回合稳定"
        if "过牌" in text or "运转" in text or "能量" in text:
            return "过牌和运转"
        if "路线支点" in text or "路线" in text or "核心" in text:
            return "明确的路线支点"
        if "长期成长" in text:
            return "长期成长"
        if "战力" in text or "输出" in text:
            return "眼前战力"
        if profile.missing_pieces:
            return profile.missing_pieces[0]
        if profile.next_picks:
            return profile.next_picks[0]
        return "能让回合更稳的直接强度"

    def _recommend_shop(self, snapshot: GameSnapshot) -> RecommendationResult | None:
        shop = snapshot.context.shop
        if shop is None:
            return None

        gold = snapshot.gold or 0
        floor = snapshot.floor or 0

        remove_target = self._best_remove_target(snapshot)
        remove_value = self._score_remove_value(snapshot, remove_target)
        remove_cost = shop.purge_cost if shop.purge_available else None

        best_card = self._best_shop_card(snapshot)
        best_relic = self._best_shop_relic(snapshot)
        best_potion = self._best_shop_potion(snapshot)

        candidates: list[tuple[float, str, str | None, list[str], str | None]] = []

        if (
            shop.purge_available
            and remove_cost is not None
            and remove_target is not None
            and gold >= remove_cost
        ):
            reasons = [
                f"当前这家商店删掉“{remove_target}”能最直接提升抽牌质量和后续回合稳定性。",
                f"删除费用是 {remove_cost} 金，当前有 {gold} 金，资源上能承担。",
            ]
            if remove_value >= 0.78:
                reasons.append("以你现在的套牌密度来看，先精简基础废牌通常比买边角补件更稳。")
            else:
                reasons.append("这次删牌有价值，但优先级还要和高质量商品比较。")
            candidates.append(
                (
                    remove_value,
                    "REMOVE",
                    remove_target,
                    self._shop_alternatives(snapshot, exclude_name=remove_target),
                    self._shop_build_direction(snapshot, focus="remove"),
                )
            )

        if best_card is not None and best_card.price is not None and gold >= best_card.price:
            card_score = self._score_shop_card(snapshot, best_card)
            reasons = self._shop_card_reasons(snapshot, best_card)
            candidates.append(
                (
                    card_score,
                    "BUY_CARD",
                    self._card_name(best_card),
                    reasons,
                    self._shop_build_direction(snapshot, focus=best_card.id),
                )
            )

        if best_relic is not None and best_relic.price is not None and gold >= best_relic.price:
            relic_score = self._score_shop_relic(best_relic)
            reasons = [
                f"{best_relic.name}对当前商店资源的转化效率更高。",
                "如果你这局更缺长期收益或体系支点，优先买遗物会更值。"
            ]
            candidates.append(
                (
                    relic_score,
                    "BUY_RELIC",
                    best_relic.name,
                    reasons,
                    self._shop_build_direction(snapshot, focus=best_relic.id),
                )
            )

        if best_potion is not None and best_potion.price is not None and gold >= best_potion.price:
            potion_score = 0.28
            reasons = [
                f"{best_potion.name}更适合当作短期补强，帮你应对接下来的战斗节点。",
                "如果你准备马上打精英或血线危险，药水价值会抬高。"
            ]
            candidates.append(
                (
                    potion_score,
                    "BUY_POTION",
                    best_potion.name,
                    reasons,
                    self._shop_build_direction(snapshot, focus=best_potion.id),
                )
            )

        if not candidates:
            return RecommendationResult(
                screen_type=snapshot.context.screen_type,
                suggested_action="LEAVE",
                primary_target=None,
                reasoning=(
                    "当前这家商店没有你买得起的高价值选项。\n"
                    "这时候先保留金币，通常比硬买边角资源更稳。\n"
                    "等更关键的商店或奖励节点再花钱，收益会更高。"
                ),
                build_direction="先保留金币，等待更高价值节点",
                alternatives=[],
                raw_response={"rule_based": True, "method": "shop"},
            )

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, action, target, reasons, build_direction = candidates[0]
        alternative_targets = [
            item[2]
            for item in candidates[1:4]
            if item[2] and item[2] != target
        ]

        if action != "REMOVE" and remove_target is not None and remove_cost is not None and remove_cost <= gold:
            if remove_value >= best_score + 0.08:
                action = "REMOVE"
                target = remove_target
                reasons = [
                    f"当前最值的是先删掉“{remove_target}”。",
                    f"删牌费用是 {remove_cost} 金，能直接提高后续抽到核心牌的概率。",
                    "以你现在的套牌质量来看，精简通常比补一张一般商品更赚。"
                ]
                build_direction = self._shop_build_direction(snapshot, focus="remove")

        return RecommendationResult(
            screen_type=snapshot.context.screen_type,
            suggested_action=action,
            primary_target=target,
            reasoning="\n".join(reasons[:3]),
            build_direction=build_direction,
            alternatives=alternative_targets[:3],
            raw_response={"rule_based": True, "method": "shop"},
        )

    def _recommend_card_reward(self, snapshot: GameSnapshot) -> RecommendationResult | None:
        reward = snapshot.context.card_reward
        if reward is None or not reward.cards:
            return None

        floor = snapshot.floor or 0
        build_profile = self.build_profiles.evaluate(snapshot)
        general_note = self.community.general_note(snapshot.character_class, floor)
        evaluations = sorted(
            (self._evaluate_reward_card(snapshot, card) for card in reward.cards),
            key=lambda item: item.score,
            reverse=True,
        )
        best = evaluations[0]
        best_name = self._card_name(best.card)
        alternatives = [self._card_name(item.card) for item in evaluations[1:3]]
        low_value_threshold = 0.05
        source_ids: tuple[str, ...] = ()

        if reward.bowl_available and best.score < low_value_threshold:
            reasoning_lines = self._dedupe_lines(
                [
                    "这组三张牌都不算当前套牌最想要的强补。",
                    f"当前构筑是“{build_profile.name}”，先保血量和容错，比硬拿一张不契合的牌更稳。",
                    self._preserve_route_line(build_profile),
                ]
            )
            return RecommendationResult(
                screen_type=snapshot.context.screen_type,
                suggested_action="BOWL",
                primary_target=None,
                reasoning="\n".join(reasoning_lines[:3]),
                build_direction="先保血量与容错，再等关键补强",
                alternatives=alternatives,
                raw_response={
                    "rule_based": True,
                    "method": "card_reward",
                    "build_profile": build_profile.to_dict(),
                    "fit_label": "不契合当前构筑",
                    "route_after_pick": "维持当前路线",
                    "confidence": 0.72,
                    "opportunity_cost": "拿汤会放弃这次即时补强，但能把容错和后续路线弹性保住。",
                    "community_sources": self.community.sources_for_ids(source_ids),
                },
            )

        if reward.skip_available and best.score < -0.15:
            reasoning_lines = self._dedupe_lines(
                [
                    "这组三张牌都不够解决当前套牌最直接的问题。",
                    f"当前构筑是“{build_profile.name}”，这几张里没有一张能稳定补上你现在最缺的那块。",
                    self._preserve_route_line(build_profile),
                ]
            )
            return RecommendationResult(
                screen_type=snapshot.context.screen_type,
                suggested_action="SKIP",
                primary_target=None,
                reasoning="\n".join(reasoning_lines[:3]),
                build_direction="先保牌组质量，再等核心路线牌",
                alternatives=[best_name, *alternatives][:3],
                raw_response={
                    "rule_based": True,
                    "method": "card_reward",
                    "build_profile": build_profile.to_dict(),
                    "fit_label": "不契合当前构筑",
                    "route_after_pick": "维持当前路线",
                    "confidence": 0.78,
                    "opportunity_cost": "跳过会放弃这次拿牌机会，但能避免把无关散件塞进套牌。",
                    "community_sources": self.community.sources_for_ids(source_ids),
                },
            )

        reasons = list(best.reasons)
        best_note = self.community.card_note(snapshot.character_class, best.card.id, floor)
        if best_note is not None:
            source_ids = tuple(dict.fromkeys((*source_ids, *best_note.source_ids)))
        if general_note is not None:
            source_ids = tuple(dict.fromkeys((*source_ids, *general_note.source_ids)))
        if len(reasons) < 3:
            reasons.append("它比当前其他候选更不容易卡手，也更贴合现在的回合节奏。")

        reasoning_lines = self._dedupe_lines(
            [
                self._fit_summary_line(build_profile, best),
                *reasons,
                self._route_after_pick_line(build_profile, best),
                self._compare_to_other_candidates(best, evaluations[1:]),
            ]
        )
        reasoning = "\n".join(reasoning_lines[:4])
        return RecommendationResult(
            screen_type=snapshot.context.screen_type,
            suggested_action="TAKE",
            primary_target=best_name,
            reasoning=reasoning,
            build_direction=best.build_direction,
            alternatives=alternatives,
            raw_response={
                "rule_based": True,
                "method": "card_reward",
                "build_profile": build_profile.to_dict(),
                "fit_label": best.fit_label,
                "route_after_pick": best.route_after_pick,
                "route_family": best.route_family,
                "confidence": self._confidence_from_gap(best.score - (evaluations[1].score if len(evaluations) > 1 else 0.0)),
                "opportunity_cost": self._card_opportunity_cost(best_name, evaluations[1:3]),
                "learning_rule": self._learning_rule_for_reward(snapshot, best),
                "fills_gap": self._fills_gap_for_reward(snapshot, build_profile, best),
                "safe_default": self._safe_default_for_reward(snapshot, best),
                "scores": [
                    {
                        "card": self._card_name(item.card),
                        "score": round(item.score, 3),
                        "fit_score": round(item.fit_score, 3),
                        "fit_label": item.fit_label,
                        "route_after_pick": item.route_after_pick,
                    }
                    for item in evaluations
                ],
                "community_sources": self.community.sources_for_ids(source_ids),
            },
        )

    def _evaluate_reward_card(self, snapshot: GameSnapshot, card: CardSnapshot) -> _RewardEvaluation:
        score = 0.0
        reasons: list[str] = []
        build_direction = "先补当前强度与运转"
        card_name = self._card_name(card)
        floor = snapshot.floor or 0
        character = (snapshot.character_class or "").upper()
        build_profile = self.build_profiles.evaluate(snapshot)
        community_note = self.community.card_note(snapshot.character_class, card.id, floor)
        general_note = self.community.general_note(snapshot.character_class, floor)

        if card.cost is not None:
            if card.cost == 0:
                score += 0.22
            elif card.cost == 1:
                score += 0.16
            elif card.cost >= 2:
                score -= 0.18 * (card.cost - 1)

        rarity = (card.rarity or "").upper()
        if rarity == "UNCOMMON":
            score += 0.12
        elif rarity == "RARE":
            score += 0.24

        card_type = (card.type or "").upper()
        if card_type == "SKILL":
            score += 0.08
        elif card_type == "POWER":
            score += 0.04 if floor >= 6 else -0.08

        if card.exhausts:
            score -= 0.06

        if community_note is not None:
            score += community_note.score_adjustment
            reasons.extend(community_note.reason_lines)
            build_direction = community_note.build_direction

        lowered_id = card.id.casefold()
        lowered_name = card_name.casefold()

        if character == "THE_SILENT":
            if card.id == "Dodge and Roll":
                score += 0.95
                reasons.extend(
                    [
                        f"{card_name}立刻补足静默开局最缺的防御质量，前几层会稳很多。",
                        "先把容错和掉血控制住，后续更容易转敏捷、毒或过牌体系。",
                    ]
                )
                build_direction = "先走稳健防御，再接敏捷或毒"
            elif card.id == "Calculated Gamble":
                score += 0.34
                reasons.extend(
                    [
                        f"{card_name}能提前补过牌与换手质量，后面更容易接弃牌运转。",
                        "它偏中期发力，第一层拿到不会立刻爆强，但成长空间不错。",
                    ]
                )
                build_direction = "提前铺过牌与弃牌运转"
            elif card.id == "Underhanded Strike":
                score -= 0.42
                reasons.extend(
                    [
                        f"{card_name}是两费攻击，开局容易卡手，节奏不如一费稳牌顺。",
                        "静默第一幕通常更怕掉血和回合发僵，不太想先补笨重输出。",
                    ]
                )
                build_direction = "只当临时输出补丁，不建议主抓"
        elif character == "IRONCLAD":
            if card.id == "PommelStrike":
                score += 0.72
                reasons.extend(
                    [
                        f"{card_name}是高质量前期攻击，还顺手补过牌，能明显提升回合效率。",
                        "它和重击的易伤节奏衔接很好，第一幕非常实用。",
                    ]
                )
                build_direction = "先补输出与过牌节奏"
            elif card.id == "ShrugItOff":
                score += 0.64
                reasons.extend(
                    [
                        f"{card_name}同时给格挡和过牌，属于很稳的铁甲过渡牌。",
                        "如果前几层担心掉血，它是安全感很高的选择。",
                    ]
                )
                build_direction = "先补稳健防御与过牌"
            elif card.id == "Inflame":
                score += 0.38
                reasons.extend(
                    [
                        f"{card_name}能提前准备力量成长线，但前几层即时战力不如优质攻防牌。",
                        "如果当前更想稳过第一幕，优先级会略低一点。",
                    ]
                )
                build_direction = "提前布局力量成长线"

        if not reasons:
            if card_type == "SKILL":
                reasons.append(f"{card_name}更偏稳定与运转，能先补当前回合质量。")
                build_direction = "先补防御与运转"
            elif card_type == "POWER":
                reasons.append(f"{card_name}偏长期成长，适合在当前强度足够时提前布局。")
                build_direction = "先铺成长，再补当前战力"
            else:
                reasons.append(f"{card_name}更偏直接战力，适合先补当前输出节奏。")
                build_direction = "先补前期输出节奏"

        if floor <= 3 and card_type == "POWER":
            reasons.append("第一幕前段更看重即时收益，所以这类慢牌通常要和当前血量一起考虑。")
        if "strike" in lowered_id and card.cost and card.cost >= 2:
            score -= 0.16
        if "draw" in lowered_name or "gamble" in lowered_name or "pommel" in lowered_name:
            score += 0.14
        if "defend" in lowered_name or "survivor" in lowered_name or "roll" in lowered_name:
            score += 0.18
        if general_note is not None:
            reasons.extend(general_note.reason_lines[:1])

        fit_score, fit_label, route_after_pick, route_family, fit_reason = self._build_fit_for_card(
            snapshot=snapshot,
            profile=build_profile,
            card=card,
        )
        score += fit_score
        reasons.append(fit_reason)
        build_direction = route_after_pick or build_direction

        return _RewardEvaluation(
            card=card,
            score=score,
            reasons=self._dedupe_lines(reasons),
            build_direction=build_direction,
            fit_score=fit_score,
            fit_label=fit_label,
            route_after_pick=route_after_pick,
            route_family=route_family,
        )

    def _recommend_combat(self, snapshot: GameSnapshot) -> RecommendationResult | None:
        hand_cards = self._extract_hand_cards(snapshot.raw_game_state)
        energy = self._extract_energy(snapshot.raw_game_state)
        incoming_damage = self._estimate_incoming_damage(snapshot.raw_game_state)
        attackers = self._count_attackers(snapshot.raw_game_state)

        sequence = self._build_combat_sequence(hand_cards, energy, incoming_damage)
        first_card = sequence[0] if sequence else None
        build_direction = "先减伤再补输出" if incoming_damage > 0 else "无压时先成长再打伤害"
        block_threshold = incoming_damage
        potion_hint = self._combat_potion_hint(incoming_damage=incoming_damage, attackers=attackers, energy=energy)
        opportunity_cost = (
            "这回合如果先贪成长，最容易白吃一轮伤害。"
            if incoming_damage > 0
            else "这回合压力不大，别把高质量成长牌留到太晚。"
        )

        reasons: list[str] = []
        if sequence:
            if len(sequence) == 1:
                reasons.append(f"这回合优先把{sequence[0]}先打出去。")
            else:
                reasons.append(f"这回合建议顺序：{' -> '.join(sequence[:3])}。")
        else:
            reasons.append("当前没抓到明确的关键牌，先按减伤优先的思路处理。")

        if incoming_damage > 0:
            reasons.append(f"对面这回合大约会打你 {incoming_damage} 点，先把减伤和格挡放前面。")
        else:
            reasons.append("这回合伤害压力不大，可以先下成长、过牌或高质量输出。")

        if attackers >= 2:
            reasons.append("多目标战斗里，先压正在攻击的敌人，避免白吃多段伤害。")
        else:
            reasons.append("如果已经能斩杀威胁怪，最后的能量优先补输出。")

        return RecommendationResult(
            screen_type=snapshot.context.screen_type,
            suggested_action="PLAY_SEQUENCE",
            primary_target=first_card,
            reasoning="\n".join(self._dedupe_lines(reasons)[:3]),
            build_direction=build_direction,
            alternatives=sequence[1:3],
            raw_response={
                "rule_based": True,
                "method": "combat",
                "energy": energy,
                "incoming_damage": incoming_damage,
                "attackers": attackers,
                "hand": [card.name for card in hand_cards],
                "play_sequence": sequence[:5],
                "block_threshold": block_threshold,
                "potion_hint": potion_hint,
                "opportunity_cost": opportunity_cost,
            },
        )

    def _recommend_relic_reward(self, snapshot: GameSnapshot) -> RecommendationResult | None:
        relic_reward = snapshot.context.relic_reward
        if relic_reward is None:
            return None

        build_profile = self.build_profiles.evaluate(snapshot)
        floor = snapshot.floor or 0
        hp_ratio = self._hp_ratio(snapshot)

        scored_relics: list[tuple[float, Any, list[str]]] = []
        for relic in relic_reward.relics:
            score, reasons = self._score_relic_in_run_context(
                snapshot=snapshot,
                relic=relic,
                build_profile=build_profile,
                floor=floor,
                hp_ratio=hp_ratio,
            )
            scored_relics.append((score, relic, reasons))
        scored_relics.sort(key=lambda item: item[0], reverse=True)

        best_score = scored_relics[0][0] if scored_relics else -999.0
        best_relic = scored_relics[0][1] if scored_relics else None
        best_reasons = scored_relics[0][2] if scored_relics else []

        key_score, key_reasons = self._score_sapphire_key_choice(
            snapshot=snapshot,
            build_profile=build_profile,
            floor=floor,
            hp_ratio=hp_ratio,
            linked_relic=relic_reward.linked_relic,
        )

        if relic_reward.sapphire_key_available and key_score >= best_score + 0.04:
            alternatives: list[str] = []
            if best_relic is not None:
                alternatives.append(best_relic.name)
            for _, relic, _ in scored_relics[1:3]:
                if relic.name not in alternatives:
                    alternatives.append(relic.name)
            return RecommendationResult(
                screen_type=snapshot.context.screen_type,
                suggested_action="TAKE",
                primary_target="蓝钥匙",
                reasoning="\n".join(key_reasons[:3]),
                build_direction="在当前路线里提前规划心脏线资源",
                alternatives=alternatives[:3],
                raw_response={
                    "rule_based": True,
                    "method": "relic_reward",
                    "source": relic_reward.source,
                    "picked": "SAPPHIRE_KEY",
                    "best_relic_score": round(best_score, 3),
                    "key_score": round(key_score, 3),
                    "confidence": self._confidence_from_gap(key_score - best_score),
                    "opportunity_cost": f"现在放弃{best_relic.name}，换来整局蓝钥匙进度。"
                    if best_relic is not None
                    else "现在放弃眼前遗物，换来整局蓝钥匙进度。",
                },
            )

        if best_relic is None:
            return None

        alternatives = [relic.name for _, relic, _ in scored_relics[1:4]]
        if relic_reward.sapphire_key_available:
            alternatives = ["蓝钥匙", *alternatives]
        return RecommendationResult(
            screen_type=snapshot.context.screen_type,
            suggested_action="TAKE",
            primary_target=best_relic.name,
            reasoning="\n".join(best_reasons[:3]),
            build_direction=self._relic_build_direction(snapshot, build_profile, best_relic.id),
            alternatives=alternatives[:3],
            raw_response={
                "rule_based": True,
                "method": "relic_reward",
                "source": relic_reward.source,
                "picked": best_relic.id,
                "confidence": self._confidence_from_gap(best_score - key_score),
                "opportunity_cost": (
                    "如果现在不拿，后面未必还有同等质量的长期收益遗物。"
                    if best_score >= 0.72
                    else "如果现在不拿，后面可能还是要用别的资源来补这块短板。"
                ),
                "scores": [
                    {
                        "id": relic.id,
                        "name": relic.name,
                        "score": round(score, 3),
                    }
                    for score, relic, _ in scored_relics
                ],
                "key_score": round(key_score, 3) if relic_reward.sapphire_key_available else None,
            },
        )

    def _best_remove_target(self, snapshot: GameSnapshot) -> str | None:
        priority_order = (
            "Strike_R",
            "Strike_G",
            "Strike_B",
            "Strike_P",
            "Defend_R",
            "Defend_G",
            "Defend_B",
            "Defend_P",
        )
        counts: dict[str, int] = {}
        for card in snapshot.deck:
            counts[card.id] = counts.get(card.id, 0) + 1

        for card_id in priority_order:
            if counts.get(card_id, 0) > 0:
                return resolve_card_name(card_id, None)
        return None

    def _score_relic_in_run_context(
        self,
        snapshot: GameSnapshot,
        relic,
        build_profile: BuildProfile,
        floor: int,
        hp_ratio: float,
    ) -> tuple[float, list[str]]:
        owned_relic_ids = {owned.id.casefold() for owned in snapshot.relics}
        deck_ids = [card.id.casefold() for card in snapshot.deck]
        deck_size = len(snapshot.deck)
        lowered = relic.id.casefold()

        score = 0.45
        reasons = [
            f"{relic.name}对当前这局不是孤立提升，而是会直接改变后面几层的资源转化效率。",
        ]

        if relic.id.casefold() in owned_relic_ids:
            score -= 0.5
            reasons.append("这件遗物和你当前持有内容重复，实际收益会明显变低。")

        if floor <= 18:
            score += 0.1
            reasons.append("现在还在中前段楼层，长期成长型遗物通常更容易把价值吃满。")
        else:
            reasons.append("这时更看重能不能立刻补当前短板，而不是只讲远期想象空间。")

        if hp_ratio <= 0.45:
            if any(token in lowered for token in ("anchor", "thread", "horncleat", "incense", "meat", "blood", "mango", "pear", "waffle")):
                score += 0.22
                reasons.append("你现在血线偏紧，能直接减伤、补容错或稳开局的遗物优先级会抬高。")
            elif any(token in lowered for token in ("black star", "astrolabe", "question", "shovel", "girya")):
                score -= 0.08

        if build_profile.archetype_key:
            if "silent_shiv" in build_profile.archetype_key and any(
                token in lowered for token in ("kunai", "shuriken", "ornamental fan", "wristblade", "ninja")
            ):
                score += 0.28
                reasons.append("它和你现在的出牌频率型路线契合度很高，能把整局节奏一起抬起来。")
            if "silent_poison" in build_profile.archetype_key and any(
                token in lowered for token in ("snecko skull", "specimen", "twisted funnel")
            ):
                score += 0.28
                reasons.append("它能把当前毒体系的核心收益继续放大，不只是锦上添花。")
            if "silent_discard" in build_profile.archetype_key and any(
                token in lowered for token in ("tough bandages", "tingsha", "hovering kite")
            ):
                score += 0.28
                reasons.append("它和弃牌运转是强联动，拿到后整套牌组的方向会更明确。")
            if "ironclad_exhaust" in build_profile.archetype_key and any(
                token in lowered for token in ("dead branch", "charon's ashes", "medical kit")
            ):
                score += 0.3
                reasons.append("它和废牌线是整局级联动，属于会明显改写后续抓牌标准的类型。")
            if "ironclad_strength" in build_profile.archetype_key and any(
                token in lowered for token in ("champion belt", "paper frog", "vajra", "shuriken")
            ):
                score += 0.2
            if "defect_frost_focus" in build_profile.archetype_key and any(
                token in lowered for token in ("data disk", "frozen core", "emotion chip", "gold plated cables")
            ):
                score += 0.26
                reasons.append("它和机器人球体成长线贴合，能同时增强防守和终局上限。")
            if "defect_orb" in build_profile.archetype_key and any(
                token in lowered for token in ("data disk", "gold plated cables", "inserter", "runic capacitor")
            ):
                score += 0.24
            if "watcher" in build_profile.archetype_key and any(
                token in lowered for token in ("violet lotus", "teardrop", "duality", "incense")
            ):
                score += 0.24

        if any(token in lowered for token in ("runic pyramid", "well laid plans")):
            if deck_size <= 15:
                score += 0.18
                reasons.append("你现在牌组还不厚，保留关键牌会比硬拼即时抽牌更强。")
            else:
                score += 0.08

        if "black star" in lowered:
            if floor <= 20:
                score += 0.2
                reasons.append("你还有足够多的精英可打，这件遗物的滚雪球价值还来得及兑现。")
            else:
                score -= 0.02
        if "astrolabe" in lowered:
            base_cards = sum(1 for card_id in deck_ids if "strike_" in card_id or "defend_" in card_id)
            if base_cards >= 5:
                score += 0.2
                reasons.append("你套牌里基础牌还不少，变牌收益比较真实，不是空想。")
        if any(token in lowered for token in ("busted crown", "sozu", "ectoplasm", "coffee dripper", "fusion hammer", "philosopher's stone")):
            score -= 0.18
            reasons.append("它的副作用会明显改变后续资源节奏，只有在特别契合当前局面时才值得硬拿。")
        if "tiny house" in lowered:
            score -= 0.16
            reasons.append("它给的东西比较分散，通常不如能明确补强路线的遗物。")

        deduped = self._dedupe_lines(reasons)
        return score, deduped[:4]

    def _score_sapphire_key_choice(
        self,
        snapshot: GameSnapshot,
        build_profile: BuildProfile,
        floor: int,
        hp_ratio: float,
        linked_relic,
    ) -> tuple[float, list[str]]:
        score = -0.05
        reasons = ["蓝钥匙是整局规划资源，不是当前这一层的即时战力。"]

        if floor >= 30:
            score += 0.28
            reasons.append("已经接近后期，再不拿蓝钥匙，后面能补的窗口会越来越少。")
        elif floor >= 17:
            score += 0.18
            reasons.append("现在开始补蓝钥匙是比较自然的时间点，不容易把后面路线压得太死。")
        else:
            reasons.append("楼层还偏早，如果要放弃一件好遗物，机会成本往往偏高。")

        if hp_ratio >= 0.6:
            score += 0.06
        else:
            score -= 0.04

        if build_profile.rating.upper() in {"S", "A"}:
            score += 0.08
            reasons.append("你当前这局成型感不错，提前为心脏线留资源更有意义。")

        if linked_relic is not None:
            linked_score, _ = self._score_relic_in_run_context(
                snapshot=snapshot,
                relic=linked_relic,
                build_profile=build_profile,
                floor=floor,
                hp_ratio=hp_ratio,
            )
            score -= max(0.0, linked_score - 0.38)
            if linked_score >= 0.62:
                reasons.append(f"但这次放弃的 {linked_relic.name} 本身不差，所以不一定值得现在就拿钥匙。")

        return score, self._dedupe_lines(reasons)[:4]

    def _confidence_from_gap(self, gap: float) -> float:
        if gap >= 0.3:
            return 0.92
        if gap >= 0.18:
            return 0.84
        if gap >= 0.08:
            return 0.74
        return 0.62

    def _card_opportunity_cost(self, best_name: str, alternatives: list[_RewardEvaluation]) -> str:
        if not alternatives:
            return f"如果现在不拿{best_name}，你大概率只能拿到更弱的即时补丁。"
        runner_up = self._card_name(alternatives[0].card)
        return f"如果不拿{best_name}，这次多半就只能退而求其次拿{runner_up}，即时强度会更亏。"

    def _learning_rule_for_reward(self, snapshot: GameSnapshot, evaluation: _RewardEvaluation) -> str:
        floor = snapshot.floor or 0
        card_type = (evaluation.card.type or "").upper()
        if floor <= 6 and evaluation.card.cost is not None and evaluation.card.cost >= 2:
            return "第一幕前几层先拿不卡手、能立刻减少掉血的牌，慢热高费牌先别急着贪。"
        if floor <= 6 and card_type == "SKILL":
            return "新手前几层先把回合质量做顺，比硬补笨重输出更容易稳住血线。"
        if evaluation.fit_score >= 0.14:
            return "拿牌时先看它是不是在补你当前路线，而不是只看它单卡强不强。"
        return "拿牌时先解决当前最明显的短板，别急着为了想象中的后期强行转路线。"

    def _fills_gap_for_reward(
        self,
        snapshot: GameSnapshot,
        profile: BuildProfile,
        evaluation: _RewardEvaluation,
    ) -> str:
        del snapshot
        del profile
        card_name = self._card_name(evaluation.card)
        card_type = (evaluation.card.type or "").upper()
        if evaluation.route_family in {"defense", "dex", "frost_focus", "block"}:
            return f"{card_name}主要是在补你现在最缺的防守和回合稳定，不容易一层层白掉血。"
        if evaluation.route_family in {"discard", "poison", "shiv", "strength", "stance"}:
            return f"{card_name}是在给当前构筑补路线支点，拿了以后后面更知道该继续找什么。"
        if card_type == "SKILL":
            return f"{card_name}主要补的是回合质量，让你更容易把手牌和能量用顺。"
        if card_type == "POWER":
            return f"{card_name}补的是长期成长，但前提是你当前已经能稳住前几回合。"
        return f"{card_name}补的是眼前战力，能让这一幕的战斗更快结束。"

    def _safe_default_for_reward(self, snapshot: GameSnapshot, evaluation: _RewardEvaluation) -> str:
        card_name = self._card_name(evaluation.card)
        if evaluation.fit_score >= 0.14:
            return f"如果你拿不准，这次先照着拿“{card_name}”通常最稳，因为它不会把当前路线带偏。"
        reward = snapshot.context.card_reward
        if reward is not None and reward.skip_available:
            return "如果你还是拿不准，宁可先跳过，也别为了不空过硬拿一张以后可能会卡手的牌。"
        return f"如果你拿不准，这次先照着拿“{card_name}”，至少能补到当前最直接的缺口。"

    def _combat_potion_hint(self, incoming_damage: int, attackers: int, energy: int | None) -> str:
        if incoming_damage >= 18:
            return "如果手里没法稳住这轮，药水可以直接考虑交。"
        if attackers >= 2 and incoming_damage >= 10:
            return "多目标高压局可以提前交群体减伤或爆发药水，别硬贪。"
        if energy == 0 and incoming_damage > 0:
            return "这回合能量已经很紧，药水价值会比硬吃伤害更高。"
        return "药水先留着，但下一回合如果继续高压就别省。"

    def _relic_build_direction(
        self,
        snapshot: GameSnapshot,
        build_profile: BuildProfile,
        relic_id: str,
    ) -> str:
        lowered = relic_id.casefold()
        if any(token in lowered for token in ("kunai", "shuriken", "ornamental fan", "wristblade")):
            return "继续优先补高频出牌与回合质量"
        if any(token in lowered for token in ("snecko skull", "specimen", "twisted funnel")):
            return "继续往毒体系深走，把持续伤害收益吃满"
        if any(token in lowered for token in ("tough bandages", "tingsha", "hovering kite")):
            return "继续往弃牌运转深走，优先找联动组件"
        if any(token in lowered for token in ("data disk", "gold plated cables", "runic capacitor", "emotion chip")):
            return "继续补球体与聚焦组件，让中后期强度更完整"
        general = self.community.general_note(snapshot.character_class, snapshot.floor or 0)
        if general is not None:
            return general.build_direction
        return f"围绕{build_profile.name}继续补当前最缺的那块"

    def _hp_ratio(self, snapshot: GameSnapshot) -> float:
        current_hp = snapshot.current_hp or 0
        max_hp = snapshot.max_hp or 1
        if max_hp <= 0:
            return 0.0
        return current_hp / max_hp

    def _score_remove_value(self, snapshot: GameSnapshot, target: str | None) -> float:
        if not target:
            return 0.0
        deck_size = max(1, len(snapshot.deck))
        gold = snapshot.gold or 0
        floor = snapshot.floor or 0
        base = 0.64 if "打击" in target else 0.52
        if deck_size <= 12:
            base += 0.12
        elif deck_size <= 15:
            base += 0.06
        if gold >= 150:
            base -= 0.05
        if floor <= 6:
            base += 0.08
        return base

    def _best_shop_card(self, snapshot: GameSnapshot) -> CardSnapshot | None:
        shop = snapshot.context.shop
        if shop is None or not shop.cards:
            return None
        scored = sorted(
            shop.cards,
            key=lambda card: self._score_shop_card(snapshot, card),
            reverse=True,
        )
        return scored[0]

    def _score_shop_card(self, snapshot: GameSnapshot, card: CardSnapshot) -> float:
        evaluation = self._evaluate_reward_card(snapshot, card)
        score = evaluation.score
        price = card.price or 0
        if price <= 60:
            score += 0.12
        elif price <= 90:
            score += 0.04
        elif price >= 150:
            score -= 0.18
        return score

    def _shop_card_reasons(self, snapshot: GameSnapshot, card: CardSnapshot) -> list[str]:
        evaluation = self._evaluate_reward_card(snapshot, card)
        reasons = list(evaluation.reasons[:2])
        if card.price is not None:
            reasons.append(f"它当前售价是 {card.price} 金，和这家商店里的其他商品相比性价比更好。")
        return reasons[:3]

    def _best_shop_relic(self, snapshot: GameSnapshot):
        shop = snapshot.context.shop
        if shop is None or not shop.relics:
            return None
        scored = sorted(shop.relics, key=self._score_shop_relic, reverse=True)
        return scored[0]

    def _score_shop_relic(self, relic) -> float:
        price = relic.price or 999
        score = 0.34
        if price <= 150:
            score += 0.1
        if price >= 260:
            score -= 0.08
        lowered = relic.id.casefold()
        if "clockwork" in lowered or "frozen" in lowered or "data" in lowered:
            score += 0.18
        return score

    def _best_shop_potion(self, snapshot: GameSnapshot):
        shop = snapshot.context.shop
        if shop is None or not shop.potions:
            return None
        affordable = [potion for potion in shop.potions if potion.price is None or (snapshot.gold or 0) >= potion.price]
        return affordable[0] if affordable else None

    def _shop_alternatives(self, snapshot: GameSnapshot, exclude_name: str | None = None) -> list[str]:
        options: list[str] = []
        shop = snapshot.context.shop
        if shop is None:
            return options
        for card in shop.cards[:2]:
            name = self._card_name(card)
            if name != exclude_name:
                options.append(name)
        for relic in shop.relics[:1]:
            if relic.name != exclude_name:
                options.append(relic.name)
        return list(dict.fromkeys(options))[:3]

    def _shop_build_direction(self, snapshot: GameSnapshot, focus: str | None) -> str:
        if focus == "remove":
            return "先精简牌组，提高核心牌命中率"
        general = self.community.general_note(snapshot.character_class, snapshot.floor or 0)
        if general is not None:
            return general.build_direction
        if focus:
            return f"围绕{focus}补强当前构筑"
        return "先保证当前强度与节奏"

    def _build_fit_for_card(
        self,
        snapshot: GameSnapshot,
        profile: BuildProfile,
        card: CardSnapshot,
    ) -> tuple[float, str, str, str, str]:
        profile_name = profile.name
        archetype_key = profile.archetype_key or "generic"
        character = (snapshot.character_class or "").upper()
        card_id = card.id
        card_name = self._card_name(card)

        route_family = "generic"
        fit_score = 0.0
        route_after_pick = profile_name

        if character == "THE_SILENT":
            poison_cards = {"Deadly Poison", "Bouncing Flask", "Noxious Fumes", "Catalyst", "Crippling Cloud"}
            discard_cards = {"Acrobatics", "Calculated Gamble", "Prepared", "Tactician", "Reflex", "Sneaky Strike", "Eviscerate"}
            shiv_cards = {"Blade Dance", "Cloak And Dagger", "Infinite Blades", "Accuracy", "Finisher"}
            defense_cards = {"Dodge and Roll", "Backflip", "Footwork", "Blur", "Leg Sweep"}

            if card_id in poison_cards:
                route_family = "poison"
                route_after_pick = "往静默毒体系靠"
            elif card_id in discard_cards:
                route_family = "discard"
                route_after_pick = "往静默弃牌运转靠"
            elif card_id in shiv_cards:
                route_family = "shiv"
                route_after_pick = "往静默刀流节奏靠"
            elif card_id in defense_cards:
                route_family = "defense"
                route_after_pick = "继续补稳静默防守与运转"

            if archetype_key == "silent_poison_control":
                if route_family == "poison":
                    fit_score += 0.42
                elif route_family in {"defense", "discard"}:
                    fit_score += 0.18
                elif route_family == "shiv":
                    fit_score -= 0.14
            elif archetype_key == "silent_discard_engine":
                if route_family == "discard":
                    fit_score += 0.4
                elif route_family in {"defense", "shiv"}:
                    fit_score += 0.12
                elif route_family == "poison":
                    fit_score -= 0.08
            elif archetype_key == "silent_shiv_tempo":
                if route_family == "shiv":
                    fit_score += 0.38
                elif route_family == "defense":
                    fit_score += 0.14
                elif route_family == "poison":
                    fit_score -= 0.1
            else:
                if route_family == "defense":
                    fit_score += 0.24
                elif route_family in {"discard", "poison"}:
                    fit_score += 0.16
                elif route_family == "shiv":
                    fit_score += 0.08

        elif character == "IRONCLAD":
            strength_cards = {"Inflame", "Spot Weakness", "Limit Break", "Demon Form", "Heavy Blade", "Sword Boomerang"}
            exhaust_cards = {"Feel No Pain", "True Grit", "Burning Pact", "Fiend Fire", "Dark Embrace", "Second Wind"}
            block_cards = {"ShrugItOff", "Flame Barrier", "Impervious", "Power Through"}
            if card_id in strength_cards:
                route_family = "strength"
                route_after_pick = "继续补铁甲力量成长"
            elif card_id in exhaust_cards:
                route_family = "exhaust"
                route_after_pick = "往铁甲废牌联动走"
            elif card_id in block_cards:
                route_family = "block"
                route_after_pick = "继续补铁甲稳健底盘"

            if archetype_key == "ironclad_strength_burst":
                fit_score += 0.34 if route_family == "strength" else 0.14 if route_family == "block" else -0.06
            elif archetype_key == "ironclad_exhaust_engine":
                fit_score += 0.34 if route_family == "exhaust" else 0.16 if route_family == "block" else -0.08
            else:
                fit_score += 0.2 if route_family in {"block", "strength"} else 0.06

        elif character == "DEFECT":
            frost_focus_cards = {"Coolheaded", "Glacier", "Defragment", "Biased Cognition", "Loop", "Capacitor"}
            orb_cards = {"Ball Lightning", "Zap", "Dualcast", "Electrodynamics", "Cold Snap"}
            if card_id in frost_focus_cards:
                route_family = "frost_focus"
                route_after_pick = "往缺陷冰球聚焦走"
            elif card_id in orb_cards:
                route_family = "orb"
                route_after_pick = "继续补缺陷球体节奏"

            if archetype_key == "defect_frost_focus":
                fit_score += 0.36 if route_family == "frost_focus" else 0.12 if route_family == "orb" else 0.0
            elif archetype_key == "defect_orb_tempo":
                fit_score += 0.34 if route_family == "orb" else 0.18 if route_family == "frost_focus" else 0.0
            else:
                fit_score += 0.18 if route_family in {"frost_focus", "orb"} else 0.0

        elif character == "WATCHER":
            stance_cards = {"Eruption", "Vigilance", "Tantrum", "Inner Peace", "Fear No Evil", "Rushdown", "Talk to the Hand"}
            if card_id in stance_cards:
                route_family = "stance"
                route_after_pick = "往观者姿态切换走"
            if archetype_key in {"watcher_stance_burst", "watcher_rushdown_combo"}:
                fit_score += 0.36 if route_family == "stance" else 0.04
            else:
                fit_score += 0.2 if route_family == "stance" else 0.0

        if fit_score >= 0.32:
            fit_label = "高度契合当前构筑"
        elif fit_score >= 0.14:
            fit_label = "基本契合当前构筑"
        elif fit_score >= -0.04:
            fit_label = "偏中性，不太带偏路线"
        else:
            fit_label = "会把路线往别的方向带"

        if fit_score >= 0.14:
            fit_reason = f"{card_name}与当前“{profile_name}”{fit_label}。"
        elif route_family != "generic":
            fit_reason = f"{card_name}{fit_label}，拿了以后会更明显地把你往新路线带。"
        else:
            fit_reason = f"{card_name}对当前“{profile_name}”帮助一般，但能补一点即时强度。"

        return fit_score, fit_label, route_after_pick, route_family, fit_reason

    def _fit_summary_line(self, profile: BuildProfile, evaluation: _RewardEvaluation) -> str:
        card_name = self._card_name(evaluation.card)
        return f"当前构筑是“{profile.name}”，这次推荐拿“{card_name}”，因为它{evaluation.fit_label}。"

    def _route_after_pick_line(self, profile: BuildProfile, evaluation: _RewardEvaluation) -> str:
        route = evaluation.route_after_pick or evaluation.build_direction
        if evaluation.fit_score >= 0.14:
            return f"拿了以后会继续围绕“{profile.name}”补强，路线更偏向：{route}。"
        return f"拿了以后会把当前局面往这条路线推：{route}。"

    def _preserve_route_line(self, profile: BuildProfile) -> str:
        return f"跳过是在保留当前“{profile.name}”的路线，不让牌组被边角牌带偏。"

    def _compare_to_other_candidates(
        self,
        best: _RewardEvaluation,
        others: list[_RewardEvaluation],
    ) -> str:
        if not others:
            return "当前可选项不多，先拿最稳的一张。"
        runner_up = others[0]
        best_name = self._card_name(best.card)
        other_name = self._card_name(runner_up.card)
        if best.fit_score >= runner_up.fit_score + 0.14:
            return f"和“{other_name}”相比，“{best_name}”对当前构筑更顺，不容易把牌组带偏。"
        if best.score >= runner_up.score + 0.18:
            return f"和“{other_name}”相比，“{best_name}”对这一幕的即时提升更直接。"
        return f"“{other_name}”也能考虑，但综合当前节奏和构筑贴合度，还是“{best_name}”更稳。"

    def _build_combat_sequence(
        self,
        hand_cards: list[_CombatCard],
        energy: int | None,
        incoming_damage: int,
    ) -> list[str]:
        if not hand_cards:
            return []

        remaining_energy = energy if energy is not None else 3
        remaining_block_need = incoming_damage
        available = [card for card in hand_cards if card.playable]
        sequence: list[str] = []

        def can_afford(card: _CombatCard) -> bool:
            return card.cost is None or card.cost <= remaining_energy

        def take(card: _CombatCard) -> None:
            nonlocal remaining_energy, remaining_block_need
            if card.cost is not None:
                remaining_energy = max(0, remaining_energy - card.cost)
            sequence.append(card.name)
            remaining_block_need = max(0, remaining_block_need - self._estimated_block(card))
            available.remove(card)

        zero_pressure_cards = sorted(
            [
                card
                for card in available
                if can_afford(card) and self._is_zero_cost_setup(card, incoming_damage)
            ],
            key=self._combat_priority,
            reverse=True,
        )
        for card in zero_pressure_cards:
            take(card)

        if remaining_block_need > 0:
            while True:
                block_cards = sorted(
                    [card for card in available if can_afford(card) and self._is_block_card(card)],
                    key=self._combat_priority,
                    reverse=True,
                )
                if not block_cards:
                    break
                take(block_cards[0])
                if remaining_block_need <= 0:
                    break

        setup_cards = sorted(
            [card for card in available if can_afford(card) and self._is_setup_card(card, incoming_damage)],
            key=self._combat_priority,
            reverse=True,
        )
        for card in setup_cards:
            if card in available and can_afford(card):
                take(card)

        attack_cards = sorted(
            [card for card in available if can_afford(card)],
            key=self._combat_priority,
            reverse=True,
        )
        for card in attack_cards:
            if card in available and can_afford(card):
                take(card)

        return sequence

    def _combat_priority(self, card: _CombatCard) -> tuple[float, float]:
        lowered = card.id.casefold()
        name = card.name.casefold()
        priority = 0.0
        if lowered == "neutralize":
            priority += 6.0
        elif lowered == "survivor":
            priority += 5.2
        elif lowered.startswith("defend_"):
            priority += 4.2
        elif lowered == "bash":
            priority += 3.8
        elif card.type == "POWER":
            priority += 3.4
        elif self._is_draw_card(card):
            priority += 3.2
        elif card.type == "ATTACK":
            priority += 3.0
        elif card.type == "SKILL":
            priority += 2.8

        if "strike" in lowered or "strike" in name:
            priority += 0.2
        if card.cost is not None:
            priority += max(0.0, 1.5 - (card.cost * 0.3))

        return priority, -(card.cost or 0)

    def _is_zero_cost_setup(self, card: _CombatCard, incoming_damage: int) -> bool:
        if (card.cost or 0) != 0:
            return False
        lowered = card.id.casefold()
        if lowered == "neutralize":
            return True
        return incoming_damage == 0 and (self._is_draw_card(card) or card.type == "POWER")

    def _is_setup_card(self, card: _CombatCard, incoming_damage: int) -> bool:
        if card.type == "POWER":
            return incoming_damage <= 6
        return incoming_damage == 0 and self._is_draw_card(card)

    def _is_block_card(self, card: _CombatCard) -> bool:
        lowered = card.id.casefold()
        return (
            lowered == "survivor"
            or lowered.startswith("defend_")
            or any(
                token in lowered
                for token in (
                    "block",
                    "roll",
                    "shrugitoff",
                    "backflip",
                    "legsweep",
                    "blur",
                    "cloak",
                    "panicbutton",
                )
            )
        )

    def _is_draw_card(self, card: _CombatCard) -> bool:
        lowered = card.id.casefold()
        return any(
            token in lowered
            for token in (
                "gamble",
                "acrobat",
                "prepared",
                "backflip",
                "pommel",
                "shrugitoff",
                "skim",
            )
        )

    def _estimated_block(self, card: _CombatCard) -> int:
        lowered = card.id.casefold()
        if lowered == "survivor":
            return 8
        if lowered.startswith("defend_"):
            return 5
        if lowered == "dodge and roll":
            return 4
        if "shrugitoff" in lowered or "legsweep" in lowered:
            return 8
        if self._is_block_card(card):
            return 5
        return 0

    def _extract_hand_cards(self, payload: dict[str, Any]) -> list[_CombatCard]:
        raw_cards = self._find_first_list(payload, {"hand", "hand_cards", "cards_in_hand"})
        if raw_cards is None:
            return []

        cards: list[_CombatCard] = []
        for raw in raw_cards:
            if not isinstance(raw, dict):
                continue
            card_id = self._as_text(raw.get("id")) or "UNKNOWN_CARD"
            raw_name = self._as_text(raw.get("name"))
            cards.append(
                _CombatCard(
                    id=card_id,
                    name=resolve_card_name(card_id, raw_name),
                    cost=self._as_int(raw.get("cost")),
                    type=self._as_text(raw.get("type")),
                    playable=self._as_bool(raw.get("is_playable"), default=True),
                )
            )
        return cards

    def _extract_energy(self, payload: dict[str, Any]) -> int | None:
        return self._find_first_int(
            payload,
            {
                "energy",
                "current_energy",
                "energy_count",
                "player_energy",
                "energy_remaining",
            },
        )

    def _estimate_incoming_damage(self, payload: dict[str, Any]) -> int:
        monsters = self._find_first_list(payload, {"monsters", "enemies"})
        if monsters is None:
            return 0

        total = 0
        for monster in monsters:
            if not isinstance(monster, dict):
                continue
            if self._as_bool(monster.get("is_gone")) or self._as_bool(monster.get("escaped")):
                continue
            current_hp = self._as_int(monster.get("current_hp"))
            if current_hp is not None and current_hp <= 0:
                continue
            base_damage = self._first_present_int(
                monster,
                ("intent_damage", "move_base_damage", "base_damage", "damage"),
            )
            if base_damage is None or base_damage <= 0:
                continue
            hits = self._first_present_int(
                monster,
                ("intent_hits", "intent_multi_amt", "move_hits", "multiplier"),
            ) or 1
            total += base_damage * max(1, hits)
        return total

    def _count_attackers(self, payload: dict[str, Any]) -> int:
        monsters = self._find_first_list(payload, {"monsters", "enemies"})
        if monsters is None:
            return 0

        count = 0
        for monster in monsters:
            if not isinstance(monster, dict):
                continue
            damage = self._first_present_int(
                monster,
                ("intent_damage", "move_base_damage", "base_damage", "damage"),
            )
            if damage is not None and damage > 0:
                count += 1
        return count

    def _reply_from_recommendation(
        self,
        recommendation: RecommendationResult,
        source: str,
    ) -> AssistantReply:
        action = recommendation.suggested_action.upper()
        target = recommendation.primary_target
        if action == "TAKE":
            conclusion = f"优先拿“{target}”。" if target else "这次奖励优先拿牌。"
        elif action == "SKIP":
            conclusion = "这次更建议跳过。"
        elif action == "BOWL":
            conclusion = "这次更建议拿汤。"
        elif action == "PLAY_SEQUENCE":
            conclusion = f"这回合先从“{target}”起手。" if target else "这回合先按减伤优先顺序出牌。"
        else:
            conclusion = "先按当前局面走稳。"

        reasons = [line.strip() for line in recommendation.reasoning.splitlines() if line.strip()]
        if len(reasons) < 2:
            reasons.append("先处理当前回合最直接的收益和风险。")

        return AssistantReply(
            mode="analysis",
            source=source,
            conclusion=conclusion,
            reasons=reasons[:4],
            alternatives=recommendation.alternatives[:3],
            build_direction=recommendation.build_direction,
            raw_response={"rule_based": True, "recommendation": recommendation.to_dict()},
        )

    def _card_name(self, card: CardSnapshot) -> str:
        return resolve_card_name(card.id, card.name)

    def _find_first_list(
        self,
        payload: Any,
        target_keys: set[str],
        max_depth: int = 6,
    ) -> list[Any] | None:
        if max_depth < 0:
            return None
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key.casefold() in target_keys and isinstance(value, list):
                    return value
                found = self._find_first_list(value, target_keys, max_depth=max_depth - 1)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_first_list(item, target_keys, max_depth=max_depth - 1)
                if found is not None:
                    return found
        return None

    def _find_first_int(
        self,
        payload: Any,
        target_keys: set[str],
        max_depth: int = 6,
    ) -> int | None:
        if max_depth < 0:
            return None
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key.casefold() in target_keys:
                    parsed = self._as_int(value)
                    if parsed is not None:
                        return parsed
                found = self._find_first_int(value, target_keys, max_depth=max_depth - 1)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_first_int(item, target_keys, max_depth=max_depth - 1)
                if found is not None:
                    return found
        return None

    def _first_present_int(self, payload: dict[str, Any], keys: tuple[str, ...]) -> int | None:
        for key in keys:
            parsed = self._as_int(payload.get(key))
            if parsed is not None:
                return parsed
        return None

    def _dedupe_lines(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            text = value.strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(text)
        return deduped

    def _as_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _as_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _as_bool(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return default
