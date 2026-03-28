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
    RelicRewardState,
    RelicSnapshot,
    ShopScreenState,
)
from .display_names import resolve_card_name, resolve_potion_name, resolve_relic_name


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
        available_commands = self._extract_commands(payload)
        screen_state = self._build_screen_state(game_state)
        screen_type = self._detect_screen_type(game_state, screen_state, available_commands)
        context = RecommendationContext(
            screen_type=screen_type,
            screen_state=screen_state,
            card_reward=self.extract_card_reward(screen_type, screen_state),
            shop=self.extract_shop(screen_type, screen_state),
            relic_reward=self.extract_relic_reward(screen_type, screen_state),
        )

        return GameSnapshot(
            in_game=bool(payload.get("in_game", False)),
            ready_for_command=bool(payload.get("ready_for_command", False)),
            available_commands=available_commands,
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

    def extract_relic_reward(
        self,
        screen_type: str,
        screen_state: Mapping[str, Any],
    ) -> RelicRewardState | None:
        if screen_type not in {"BOSS_REWARD", "COMBAT_REWARD", "TREASURE", "CHEST"}:
            return None

        direct_relics = [
            self._parse_relic(relic, choice_index=index)
            for index, relic in enumerate(screen_state.get("relics", []))
            if isinstance(relic, Mapping)
        ]
        if direct_relics:
            return RelicRewardState(
                relics=direct_relics,
                source=screen_type,
            )

        rewards = screen_state.get("rewards")
        if not isinstance(rewards, list):
            return None

        relics: list[RelicSnapshot] = []
        linked_relic: RelicSnapshot | None = None
        sapphire_key_available = False
        for reward in rewards:
            if not isinstance(reward, Mapping):
                continue
            reward_type = self._as_str(reward.get("reward_type"), default="").upper()
            if reward_type == "RELIC":
                relic_payload = self._extract_relic_payload(reward)
                if relic_payload is not None:
                    relics.append(self._parse_relic(relic_payload, choice_index=len(relics)))
            elif reward_type == "SAPPHIRE_KEY":
                sapphire_key_available = True
                relic_payload = self._extract_relic_payload(reward)
                if relic_payload is not None:
                    linked_relic = self._parse_relic(relic_payload)

        if not relics and linked_relic is None and not sapphire_key_available:
            return None

        return RelicRewardState(
            relics=relics,
            source=screen_type,
            sapphire_key_available=sapphire_key_available,
            linked_relic=linked_relic,
        )

    def _unwrap_game_state(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raw_game_state = payload.get("game_state")
        if isinstance(raw_game_state, Mapping):
            return raw_game_state
        return payload

    def _build_screen_state(self, game_state: Mapping[str, Any]) -> dict[str, Any]:
        screen_state = self._as_dict(game_state.get("screen_state"))
        combat_state = self._extract_combat_state(game_state)
        if not combat_state:
            return screen_state
        merged = dict(screen_state)
        merged.update(combat_state)
        return merged

    def _extract_combat_state(self, game_state: Mapping[str, Any]) -> dict[str, Any]:
        combat_state: dict[str, Any] = {}

        hand = self._find_first_list_by_keys(
            game_state,
            {"hand", "hand_cards", "cards_in_hand"},
        )
        if hand is not None:
            combat_state["hand"] = hand

        monsters = self._find_first_list_by_keys(
            game_state,
            {"monsters", "enemies"},
        )
        if monsters is not None:
            combat_state["monsters"] = monsters

        energy = self._find_first_scalar_by_keys(
            game_state,
            {"energy", "current_energy", "energy_count", "player_energy", "energy_remaining"},
        )
        if energy is not None:
            combat_state["energy"] = energy

        return combat_state

    def _detect_screen_type(
        self,
        game_state: Mapping[str, Any],
        screen_state: Mapping[str, Any],
        available_commands: list[str],
    ) -> str:
        raw_screen_type = self._as_str(game_state.get("screen_type"), default="UNKNOWN").upper()
        if raw_screen_type not in {"", "UNKNOWN", "NONE"}:
            return raw_screen_type

        if self._looks_like_combat(screen_state):
            return "COMBAT"

        command_set = {command.upper() for command in available_commands}
        if {"PLAY", "END"} & command_set:
            return "COMBAT"

        return raw_screen_type

    def _looks_like_combat(self, payload: Mapping[str, Any]) -> bool:
        return any(
            key in payload
            for key in ("hand", "hand_cards", "cards_in_hand", "monsters", "enemies")
        )

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
        card_id = self._as_str(payload.get("id"), default="UNKNOWN_CARD")
        raw_name = self._as_optional_str(payload.get("name"))
        name = resolve_card_name(card_id, raw_name)
        return CardSnapshot(
            id=card_id,
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
        relic_id = self._as_str(payload.get("id"), default="UNKNOWN_RELIC")
        raw_name = self._as_optional_str(payload.get("name"))
        name = resolve_relic_name(relic_id, raw_name)
        return RelicSnapshot(
            id=relic_id,
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
        potion_id = self._as_str(payload.get("id"), default="UNKNOWN_POTION")
        raw_name = self._as_optional_str(payload.get("name"))
        name = resolve_potion_name(potion_id, raw_name)
        return PotionSnapshot(
            id=potion_id,
            name=name,
            can_use=self._as_optional_bool(payload.get("can_use")),
            can_discard=self._as_optional_bool(payload.get("can_discard")),
            requires_target=self._as_optional_bool(payload.get("requires_target")),
            price=self._as_optional_int(payload.get("price")),
            choice_index=self._as_optional_int(payload.get("choice_index")) or choice_index,
        )

    def _extract_relic_payload(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        for key in ("relic", "linked_relic", "link"):
            value = payload.get(key)
            if isinstance(value, Mapping):
                return value
        if "id" in payload and ("name" in payload or "counter" in payload):
            return payload
        return None

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

    def _find_first_list_by_keys(
        self,
        payload: Any,
        target_keys: set[str],
        max_depth: int = 6,
    ) -> list[Any] | None:
        if max_depth < 0:
            return None
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                if str(key).casefold() in target_keys and isinstance(value, list):
                    return list(value)
                found = self._find_first_list_by_keys(value, target_keys, max_depth=max_depth - 1)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_first_list_by_keys(item, target_keys, max_depth=max_depth - 1)
                if found is not None:
                    return found
        return None

    def _find_first_scalar_by_keys(
        self,
        payload: Any,
        target_keys: set[str],
        max_depth: int = 6,
    ) -> Any | None:
        if max_depth < 0:
            return None
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                if str(key).casefold() in target_keys and not isinstance(value, (Mapping, list)):
                    return value
                found = self._find_first_scalar_by_keys(value, target_keys, max_depth=max_depth - 1)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._find_first_scalar_by_keys(item, target_keys, max_depth=max_depth - 1)
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
