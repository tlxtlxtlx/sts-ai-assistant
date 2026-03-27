from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import (
    CardRewardState,
    CardSnapshot,
    GameSnapshot,
    PotionSnapshot,
    RecommendationContext,
    RelicSnapshot,
    ShopScreenState,
)


class StateParserError(ValueError):
    """Raised when a payload cannot be parsed into a game snapshot."""


@dataclass(slots=True)
class StateParser:
    def parse_snapshot(self, payload: Mapping[str, Any]) -> GameSnapshot:
        if not isinstance(payload, Mapping):
            raise StateParserError("Payload must be a mapping.")

        if "error" in payload:
            raise StateParserError(f"Communication Mod error: {payload['error']}")

        game_state = self._unwrap_game_state(payload)
        screen_type = self._as_str(game_state.get("screen_type"), default="UNKNOWN").upper()
        screen_state = self._as_dict(game_state.get("screen_state"))
        context = RecommendationContext(
            screen_type=screen_type,
            screen_state=screen_state,
            card_reward=self.extract_card_reward(screen_type, screen_state),
            shop=self.extract_shop(screen_type, screen_state),
        )

        return GameSnapshot(
            in_game=bool(payload.get("in_game", False)),
            ready_for_command=bool(payload.get("ready_for_command", False)),
            available_commands=self._extract_commands(payload),
            character_class=self._as_optional_str(game_state.get("class")),
            ascension_level=self._as_optional_int(game_state.get("ascension_level")),
            floor=self._as_optional_int(game_state.get("floor")),
            act=self._as_optional_int(game_state.get("act")),
            gold=self._as_optional_int(game_state.get("gold")),
            current_hp=self._as_optional_int(game_state.get("current_hp")),
            max_hp=self._as_optional_int(game_state.get("max_hp")),
            deck=self.extract_deck(game_state),
            relics=self.extract_relics(game_state),
            context=context,
            raw_game_state=dict(game_state),
        )

    def extract_deck(self, game_state: Mapping[str, Any]) -> list[CardSnapshot]:
        raw_deck = game_state.get("deck")
        if not isinstance(raw_deck, list):
            raw_deck = self._find_first_list_value(game_state, "deck")
        if not isinstance(raw_deck, list):
            return []
        return [self._parse_card(card) for card in raw_deck if isinstance(card, Mapping)]

    def extract_relics(self, game_state: Mapping[str, Any]) -> list[RelicSnapshot]:
        raw_relics = game_state.get("relics")
        if not isinstance(raw_relics, list):
            raw_relics = self._find_first_list_value(game_state, "relics")
        if not isinstance(raw_relics, list):
            return []
        return [self._parse_relic(relic) for relic in raw_relics if isinstance(relic, Mapping)]

    def extract_card_reward(
        self,
        screen_type: str,
        screen_state: Mapping[str, Any],
    ) -> CardRewardState | None:
        if screen_type != "CARD_REWARD":
            return None

        cards = [
            self._parse_card(card, choice_index=index)
            for index, card in enumerate(screen_state.get("cards", []))
            if isinstance(card, Mapping)
        ]
        return CardRewardState(
            cards=cards,
            bowl_available=bool(screen_state.get("bowl_available", False)),
            skip_available=bool(screen_state.get("skip_available", False)),
        )

    def extract_shop(
        self,
        screen_type: str,
        screen_state: Mapping[str, Any],
    ) -> ShopScreenState | None:
        if screen_type not in {"SHOP", "SHOP_SCREEN"}:
            return None

        cards = [
            self._parse_card(card, choice_index=index)
            for index, card in enumerate(screen_state.get("cards", []))
            if isinstance(card, Mapping)
        ]
        relics = [
            self._parse_relic(relic, choice_index=index)
            for index, relic in enumerate(screen_state.get("relics", []))
            if isinstance(relic, Mapping)
        ]
        potions = [
            self._parse_potion(potion, choice_index=index)
            for index, potion in enumerate(screen_state.get("potions", []))
            if isinstance(potion, Mapping)
        ]
        return ShopScreenState(
            cards=cards,
            relics=relics,
            potions=potions,
            purge_available=bool(screen_state.get("purge_available", False)),
            purge_cost=self._as_optional_int(screen_state.get("purge_cost")),
        )

    def _unwrap_game_state(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raw_game_state = payload.get("game_state")
        if isinstance(raw_game_state, Mapping):
            return raw_game_state
        return payload

    def _extract_commands(self, payload: Mapping[str, Any]) -> list[str]:
        commands = payload.get("available_commands")
        if not isinstance(commands, list):
            return []
        return [str(command).upper() for command in commands]

    def _parse_card(
        self,
        payload: Mapping[str, Any],
        choice_index: int | None = None,
    ) -> CardSnapshot:
        name = self._as_str(
            payload.get("name"),
            default=self._as_str(payload.get("id"), default="UNKNOWN_CARD"),
        )
        return CardSnapshot(
            id=self._as_str(payload.get("id"), default=name),
            name=name,
            upgrades=self._as_optional_int(payload.get("upgrades")) or 0,
            cost=self._as_optional_int(payload.get("cost")),
            type=self._as_optional_str(payload.get("type")),
            rarity=self._as_optional_str(payload.get("rarity")),
            uuid=self._as_optional_str(payload.get("uuid")),
            exhausts=self._as_optional_bool(payload.get("exhausts")),
            ethereal=self._as_optional_bool(payload.get("ethereal")),
            misc=self._as_optional_int(payload.get("misc")),
            is_playable=self._as_optional_bool(payload.get("is_playable")),
            has_target=self._as_optional_bool(payload.get("has_target")),
            price=self._as_optional_int(payload.get("price")),
            choice_index=self._as_optional_int(payload.get("choice_index")) or choice_index,
        )

    def _parse_relic(
        self,
        payload: Mapping[str, Any],
        choice_index: int | None = None,
    ) -> RelicSnapshot:
        name = self._as_str(
            payload.get("name"),
            default=self._as_str(payload.get("id"), default="UNKNOWN_RELIC"),
        )
        return RelicSnapshot(
            id=self._as_str(payload.get("id"), default=name),
            name=name,
            counter=self._as_optional_int(payload.get("counter")),
            price=self._as_optional_int(payload.get("price")),
            choice_index=self._as_optional_int(payload.get("choice_index")) or choice_index,
        )

    def _parse_potion(
        self,
        payload: Mapping[str, Any],
        choice_index: int | None = None,
    ) -> PotionSnapshot:
        name = self._as_str(
            payload.get("name"),
            default=self._as_str(payload.get("id"), default="UNKNOWN_POTION"),
        )
        return PotionSnapshot(
            id=self._as_str(payload.get("id"), default=name),
            name=name,
            can_use=self._as_optional_bool(payload.get("can_use")),
            can_discard=self._as_optional_bool(payload.get("can_discard")),
            requires_target=self._as_optional_bool(payload.get("requires_target")),
            price=self._as_optional_int(payload.get("price")),
            choice_index=self._as_optional_int(payload.get("choice_index")) or choice_index,
        )

    def _find_first_list_value(
        self,
        payload: Mapping[str, Any],
        target_key: str,
        max_depth: int = 4,
    ) -> list[Any] | None:
        if max_depth < 0:
            return None

        for key, value in payload.items():
            if key == target_key and isinstance(value, list):
                return value
            if isinstance(value, Mapping):
                found = self._find_first_list_value(value, target_key, max_depth=max_depth - 1)
                if found is not None:
                    return found
        return None

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    def _as_str(self, value: Any, default: str) -> str:
        if value is None:
            return default
        return str(value)

    def _as_optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _as_optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _as_optional_bool(self, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return None
