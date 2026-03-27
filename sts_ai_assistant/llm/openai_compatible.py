from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
import json
import re
import ssl
from typing import Any
from urllib import error, request

from sts_ai_assistant.parsing.models import GameSnapshot

from .base import AssistantReply, ChatTurn, RecommendationResult
from .prompts import (
    build_analysis_messages,
    build_chat_messages,
    build_recommendation_messages,
)


@dataclass(slots=True)
class NullLLMClient:
    def recommend(self, snapshot: GameSnapshot) -> RecommendationResult:
        return RecommendationResult(
            screen_type=snapshot.context.screen_type,
            suggested_action="LLM_NOT_CONFIGURED",
            primary_target=None,
            build_direction="尚未配置可用的外部模型。",
            reasoning=(
                "当前还没有配置可用的 LLM，系统只完成了状态整理。"
                "\n所以这次不会给出真正的模型决策。"
            ),
            alternatives=self._collect_candidates(snapshot),
            raw_response={"messages": build_recommendation_messages(snapshot)},
        )

    def analyze(
        self,
        snapshot: GameSnapshot,
        source: str,
        focus: str | None = None,
    ) -> AssistantReply:
        return AssistantReply(
            mode="analysis",
            source=source,
            conclusion="当前未配置模型，先展示局面摘要。",
            reasons=[
                f"已经收到当前{self._screen_label(snapshot.context.screen_type)}的游戏状态。",
                "奖励、商店、地图、事件和战斗都已经走统一顾问接口。",
                "配置 OpenAI 兼容模型后，这里会返回更具体的中文建议。",
            ],
            alternatives=self._collect_candidates(snapshot),
            build_direction="先保证前期强度与过牌稳定",
            raw_response={
                "messages": build_analysis_messages(snapshot, source=source, focus=focus),
            },
        )

    def chat(
        self,
        snapshot: GameSnapshot,
        source: str,
        message: str,
        history: list[ChatTurn] | None = None,
    ) -> AssistantReply:
        return AssistantReply(
            mode="chat",
            source=source,
            conclusion="当前未配置模型，只能先给你局面摘要。",
            reasons=[
                f"你的问题是：{message[:60]}",
                f"现在处于{self._screen_label(snapshot.context.screen_type)}。",
                "配置 OpenAI 兼容模型后，聊天会结合当前牌组和局面给出更细的回答。",
            ],
            alternatives=self._collect_candidates(snapshot),
            build_direction="先完成模型配置，再继续追问细节",
            raw_response={
                "messages": build_chat_messages(
                    snapshot,
                    source=source,
                    message=message,
                    history=history,
                ),
            },
        )

    def _collect_candidates(self, snapshot: GameSnapshot) -> list[str]:
        if snapshot.context.card_reward is not None:
            return [card.name for card in snapshot.context.card_reward.cards[:3]]
        if snapshot.context.shop is not None:
            items = [card.name for card in snapshot.context.shop.cards[:2]]
            items.extend(relic.name for relic in snapshot.context.shop.relics[:1])
            return items[:3]
        return []

    def _screen_label(self, screen_type: str) -> str:
        mapping = {
            "CARD_REWARD": "卡牌奖励",
            "SHOP": "商店",
            "SHOP_SCREEN": "商店",
            "MAP": "地图",
            "EVENT": "事件",
            "COMBAT_REWARD": "战斗奖励",
            "COMBAT": "战斗",
        }
        return mapping.get(screen_type.upper(), screen_type)


@dataclass(slots=True)
class OpenAICompatibleLLMClient:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 30.0
    site_url: str = "http://127.0.0.1:5173"
    app_name: str = "STS AI Assistant"

    def build_request_payload(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 420,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }

    def recommend(self, snapshot: GameSnapshot) -> RecommendationResult:
        response_json, content = self._request_messages(
            build_recommendation_messages(snapshot),
            max_tokens=420,
        )
        try:
            parsed = self._extract_json_object(content)
            result = self._parse_recommendation(snapshot, parsed, response_json)
            if not result.reasoning:
                result.reasoning = self._build_display_reasoning(snapshot, result)
            return result
        except ValueError:
            recovered = self._recover_from_freeform(snapshot, content)
            if recovered is not None:
                recovered.raw_response = {
                    "provider_response": response_json,
                    "recovered": True,
                    "content_preview": content[:1200],
                }
                recovered.reasoning = self._build_display_reasoning(snapshot, recovered)
                return recovered
            return RecommendationResult(
                screen_type=snapshot.context.screen_type,
                suggested_action="UNPARSEABLE_RESPONSE",
                primary_target=None,
                reasoning="模型没有返回可直接使用的结构化建议。",
                build_direction="先采用保守路线",
                alternatives=[],
                raw_response={
                    "provider_response": response_json,
                    "content_preview": content[:1200],
                },
            )

    def analyze(
        self,
        snapshot: GameSnapshot,
        source: str,
        focus: str | None = None,
    ) -> AssistantReply:
        response_json, content = self._request_messages(
            build_analysis_messages(snapshot, source=source, focus=focus),
            max_tokens=420,
        )
        try:
            parsed = self._extract_json_object(content)
            return self._parse_assistant_reply(
                mode="analysis",
                source=source,
                parsed=parsed,
                response_json=response_json,
            )
        except ValueError:
            return self._fallback_assistant_reply(
                snapshot=snapshot,
                mode="analysis",
                source=source,
                response_json=response_json,
                content=content,
            )

    def chat(
        self,
        snapshot: GameSnapshot,
        source: str,
        message: str,
        history: list[ChatTurn] | None = None,
    ) -> AssistantReply:
        response_json, content = self._request_messages(
            build_chat_messages(
                snapshot=snapshot,
                source=source,
                message=message,
                history=history,
            ),
            max_tokens=420,
        )
        try:
            parsed = self._extract_json_object(content)
            return self._parse_assistant_reply(
                mode="chat",
                source=source,
                parsed=parsed,
                response_json=response_json,
            )
        except ValueError:
            return self._fallback_assistant_reply(
                snapshot=snapshot,
                mode="chat",
                source=source,
                response_json=response_json,
                content=content,
                question=message,
            )

    def _request_messages(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> tuple[dict[str, Any], str]:
        payload = self.build_request_payload(messages, max_tokens=max_tokens)
        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name,
        }
        response_json = self._post_json(endpoint, body=body, headers=headers)
        return response_json, self._extract_assistant_content(response_json)

    def _post_json(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        http_request = request.Request(url, data=body, headers=headers, method="POST")
        ssl_context = ssl.create_default_context()
        try:
            with request.urlopen(
                http_request,
                context=ssl_context,
                timeout=self.timeout_seconds,
            ) as response:
                return json.load(response)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:1000]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"LLM network error: {exc}") from exc
        except JSONDecodeError as exc:
            raise RuntimeError(f"LLM returned invalid JSON: {exc}") from exc

    def _extract_assistant_content(self, response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM response did not include choices.")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise RuntimeError("LLM choice was not an object.")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("LLM response did not include a message.")

        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text is not None:
                        text_parts.append(str(text))
            if text_parts:
                return "\n".join(text_parts)

        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
        raise RuntimeError("LLM message content had an unsupported format.")

    def _extract_json_object(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()

        decoder = json.JSONDecoder()
        candidate_positions = [index for index, char in enumerate(stripped) if char == "{"]
        for start in reversed(candidate_positions):
            try:
                parsed, _ = decoder.raw_decode(stripped[start:])
            except JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("No JSON object found in model output.")

    def _parse_recommendation(
        self,
        snapshot: GameSnapshot,
        parsed: dict[str, Any],
        response_json: dict[str, Any],
    ) -> RecommendationResult:
        action = str(parsed.get("suggested_action", "UNKNOWN")).strip().upper()
        target = self._as_optional_str(parsed.get("primary_target"))
        build_direction = self._clean_short_text(parsed.get("build_direction"))
        reasoning = self._compact_reasoning(parsed.get("reasoning"))
        alternatives = self._coerce_items(parsed.get("alternatives"), limit=3)
        return RecommendationResult(
            screen_type=snapshot.context.screen_type,
            suggested_action=action or "UNKNOWN",
            primary_target=target,
            reasoning=reasoning,
            build_direction=build_direction or self._infer_build_direction("", target),
            alternatives=self._dedupe_alternatives(target, alternatives),
            raw_response={
                "provider_response": response_json,
                "parsed_content": parsed,
            },
        )

    def _parse_assistant_reply(
        self,
        mode: str,
        source: str,
        parsed: dict[str, Any],
        response_json: dict[str, Any],
    ) -> AssistantReply:
        conclusion = self._clean_short_text(parsed.get("conclusion")) or "先按当前局面保守处理。"
        reasons = self._coerce_items(parsed.get("reasons"), limit=4)
        alternatives = self._coerce_items(parsed.get("alternatives"), limit=3)
        build_direction = self._clean_short_text(parsed.get("build_direction"))
        if len(reasons) < 2:
            reasons = self._pad_reasons(
                reasons,
                [
                    "优先考虑当前屏幕最直接的收益。",
                    "避免为了远期贪心而损失当前容错。",
                    "如果信息不足，先走保守线通常更稳。",
                ],
            )
        return AssistantReply(
            mode=mode,
            source=source,
            conclusion=conclusion,
            reasons=reasons[:4],
            alternatives=alternatives[:3],
            build_direction=build_direction,
            raw_response={
                "provider_response": response_json,
                "parsed_content": parsed,
            },
        )

    def _fallback_assistant_reply(
        self,
        snapshot: GameSnapshot,
        mode: str,
        source: str,
        response_json: dict[str, Any],
        content: str,
        question: str | None = None,
    ) -> AssistantReply:
        screen_label = self._screen_label(snapshot.context.screen_type)
        if mode == "chat" and question:
            conclusion = "先按当前局面走稳，这个问题可以继续追问。"
            reasons = [
                f"你的问题是：{question[:60]}",
                f"现在处于{screen_label}，先处理眼前最直接的收益与风险。",
                "模型这次没有稳定返回结构化 JSON，所以助手先给出保守回答。",
            ]
        else:
            conclusion = f"这个{screen_label}局面先走保守线。"
            reasons = [
                "优先拿立即能提高当前容错或效率的选项。",
                "如果看不准远期组合，先保证这一层的稳定度。",
                "模型这次没有稳定返回结构化 JSON，所以先给出保守版建议。",
            ]
        return AssistantReply(
            mode=mode,
            source=source,
            conclusion=conclusion,
            reasons=reasons[:4],
            alternatives=self._collect_candidates(snapshot),
            build_direction="先保证当前强度与节奏",
            raw_response={
                "provider_response": response_json,
                "content_preview": content[:1200],
            },
        )

    def _recover_from_freeform(
        self,
        snapshot: GameSnapshot,
        text: str,
    ) -> RecommendationResult | None:
        lowered = text.lower()
        action = self._infer_action(snapshot, lowered)
        target, alternatives = self._infer_target_and_alternatives(snapshot, lowered)
        if action is None and target is None:
            return None
        return RecommendationResult(
            screen_type=snapshot.context.screen_type,
            suggested_action=action or "UNKNOWN",
            primary_target=target,
            reasoning="",
            build_direction=self._infer_build_direction(lowered, target),
            alternatives=alternatives,
        )

    def _infer_action(self, snapshot: GameSnapshot, lowered_text: str) -> str | None:
        for action in (
            "buy_card",
            "buy_relic",
            "buy_potion",
            "remove",
            "leave",
            "take",
            "skip",
            "bowl",
        ):
            if re.search(rf"\b{re.escape(action)}\b", lowered_text):
                return action.upper()

        if snapshot.context.card_reward is not None:
            if snapshot.context.card_reward.skip_available and "skip" in lowered_text:
                return "SKIP"
            if snapshot.context.card_reward.bowl_available and "bowl" in lowered_text:
                return "BOWL"
            return "TAKE"

        if snapshot.context.shop is not None:
            if "remove" in lowered_text or "purge" in lowered_text:
                return "REMOVE"
            return "LEAVE"
        return None

    def _infer_target_and_alternatives(
        self,
        snapshot: GameSnapshot,
        lowered_text: str,
    ) -> tuple[str | None, list[str]]:
        candidates: list[str] = []
        if snapshot.context.card_reward is not None:
            candidates.extend(card.name for card in snapshot.context.card_reward.cards)
        if snapshot.context.shop is not None:
            candidates.extend(card.name for card in snapshot.context.shop.cards)
            candidates.extend(relic.name for relic in snapshot.context.shop.relics)
            candidates.extend(potion.name for potion in snapshot.context.shop.potions)

        scored: list[tuple[int, str]] = []
        for name in candidates:
            score = lowered_text.count(name.lower())
            if score > 0:
                scored.append((score, name))

        if not scored:
            return None, []
        scored.sort(key=lambda item: (-item[0], item[1]))
        primary = scored[0][1]
        alternatives = [name for _, name in scored[1:3]]
        return primary, alternatives

    def _infer_build_direction(self, lowered_text: str, target: str | None) -> str:
        if "draw" in lowered_text or "cycle" in lowered_text:
            return "过牌与运转稳定性"
        if "block" in lowered_text or "defend" in lowered_text:
            return "防御稳定性"
        if "strength" in lowered_text or "scale" in lowered_text:
            return "成长与后期上限"
        if "damage" in lowered_text or "attack" in lowered_text or "tempo" in lowered_text:
            return "前期输出节奏"
        if target is not None:
            return f"围绕{target}补强当前构筑"
        return "优先保证前期强度与运转"

    def _coerce_items(self, value: Any, limit: int) -> list[str]:
        if isinstance(value, str):
            candidates = re.split(r"[\n;；]+", value)
        elif isinstance(value, list):
            candidates = value
        else:
            candidates = []

        cleaned: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            text = self._as_optional_str(item)
            if not text:
                continue
            normalized = text.strip(" -•\t")
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(normalized)
            if len(cleaned) >= limit:
                break
        return cleaned

    def _dedupe_alternatives(
        self,
        primary_target: str | None,
        alternatives: list[str],
    ) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        if primary_target:
            seen.add(primary_target.casefold())
        for item in alternatives:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= 3:
                break
        return deduped

    def _compact_reasoning(self, value: Any) -> str:
        text = self._as_optional_str(value)
        if not text:
            return ""
        parts = re.split(r"[\n。！？!?.]+", text)
        lines = [part.strip(" -•\t") for part in parts if part.strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for line in lines:
            key = line.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(line)
            if len(deduped) >= 3:
                break
        return "\n".join(deduped)

    def _pad_reasons(self, reasons: list[str], filler: list[str]) -> list[str]:
        padded = list(reasons)
        seen = {item.casefold() for item in padded}
        for item in filler:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            padded.append(item)
            if len(padded) >= 3:
                break
        return padded

    def _collect_candidates(self, snapshot: GameSnapshot) -> list[str]:
        if snapshot.context.card_reward is not None:
            return [card.name for card in snapshot.context.card_reward.cards[:3]]
        if snapshot.context.shop is not None:
            items = [card.name for card in snapshot.context.shop.cards[:2]]
            items.extend(relic.name for relic in snapshot.context.shop.relics[:1])
            return items[:3]
        return []

    def _as_optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _clean_short_text(self, value: Any) -> str | None:
        text = self._as_optional_str(value)
        if text is None:
            return None
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return None
        first_line = text.splitlines()[0].strip()
        return first_line[:60] if len(first_line) > 60 else first_line

    def _build_display_reasoning(
        self,
        snapshot: GameSnapshot,
        result: RecommendationResult,
    ) -> str:
        lines: list[str] = []
        screen = snapshot.context.screen_type.upper()
        theme_line = self._theme_sentence(screen, result)

        if screen == "CARD_REWARD":
            if result.suggested_action == "SKIP":
                lines.append("当前候选对套牌的提升有限，建议跳过。")
            elif result.suggested_action == "BOWL":
                lines.append("当前套牌更适合拿汤，优先提高最大生命。")
            else:
                target = result.primary_target or "当前候选"
                lines.append(f"当前是拿牌节点，优先选择{target}。")
        elif screen in {"SHOP", "SHOP_SCREEN"}:
            if result.suggested_action == "REMOVE":
                lines.append("当前商店里，删牌对套牌精简和抽牌质量帮助更直接。")
            elif result.suggested_action == "LEAVE":
                lines.append("当前商店选项的性价比一般，暂时保留金币更稳。")
            else:
                target = result.primary_target or "当前选项"
                lines.append(f"当前是商店决策，优先考虑{target}。")
        else:
            lines.append("已根据当前局面生成建议。")

        if theme_line:
            lines.append(theme_line)

        if result.alternatives:
            alternatives = " / ".join(result.alternatives[:2])
            lines.append(f"备选：{alternatives}。")

        deduped: list[str] = []
        seen: set[str] = set()
        for line in lines:
            normalized = line.strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
            if len(deduped) >= 3:
                break
        return "\n".join(deduped) if deduped else "已根据当前局面生成建议。"

    def _theme_sentence(self, screen: str, result: RecommendationResult) -> str:
        if result.suggested_action == "REMOVE":
            return "删掉低质量牌后，后续抽到核心牌的概率会更高。"
        if screen == "CARD_REWARD":
            return "这个选择对当前套牌的即时提升更直接，也更符合现在的节奏。"
        if screen in {"SHOP", "SHOP_SCREEN"}:
            return "它对当前资源的转化效率更高，也更贴合现在的套牌需求。"
        return ""

    def _screen_label(self, screen_type: str) -> str:
        mapping = {
            "CARD_REWARD": "卡牌奖励",
            "SHOP": "商店",
            "SHOP_SCREEN": "商店",
            "MAP": "地图",
            "EVENT": "事件",
            "COMBAT_REWARD": "战斗奖励",
            "COMBAT": "战斗",
        }
        return mapping.get(screen_type.upper(), screen_type)
