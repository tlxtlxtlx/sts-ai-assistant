from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CardSnapshot:
    id: str
    name: str
    upgrades: int = 0
    cost: int | None = None
    type: str | None = None
    rarity: str | None = None
    uuid: str | None = None
    exhausts: bool | None = None
    ethereal: bool | None = None
    misc: int | None = None
    is_playable: bool | None = None
    has_target: bool | None = None
    price: int | None = None
    choice_index: int | None = None

    @property
    def display_name(self) -> str:
        if self.upgrades > 0:
            return f"{self.name}+{self.upgrades}"
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "upgrades": self.upgrades,
            "cost": self.cost,
            "type": self.type,
            "rarity": self.rarity,
            "uuid": self.uuid,
            "exhausts": self.exhausts,
            "ethereal": self.ethereal,
            "misc": self.misc,
            "is_playable": self.is_playable,
            "has_target": self.has_target,
            "price": self.price,
            "choice_index": self.choice_index,
        }


@dataclass(slots=True)
class RelicSnapshot:
    id: str
    name: str
    counter: int | None = None
    price: int | None = None
    choice_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "counter": self.counter,
            "price": self.price,
            "choice_index": self.choice_index,
        }


@dataclass(slots=True)
class PotionSnapshot:
    id: str
    name: str
    can_use: bool | None = None
    can_discard: bool | None = None
    requires_target: bool | None = None
    price: int | None = None
    choice_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "can_use": self.can_use,
            "can_discard": self.can_discard,
            "requires_target": self.requires_target,
            "price": self.price,
            "choice_index": self.choice_index,
        }


@dataclass(slots=True)
class CardRewardState:
    cards: list[CardSnapshot] = field(default_factory=list)
    bowl_available: bool = False
    skip_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "cards": [card.to_dict() for card in self.cards],
            "bowl_available": self.bowl_available,
            "skip_available": self.skip_available,
        }


@dataclass(slots=True)
class ShopScreenState:
    cards: list[CardSnapshot] = field(default_factory=list)
    relics: list[RelicSnapshot] = field(default_factory=list)
    potions: list[PotionSnapshot] = field(default_factory=list)
    purge_available: bool = False
    purge_cost: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cards": [card.to_dict() for card in self.cards],
            "relics": [relic.to_dict() for relic in self.relics],
            "potions": [potion.to_dict() for potion in self.potions],
            "purge_available": self.purge_available,
            "purge_cost": self.purge_cost,
        }


@dataclass(slots=True)
class RelicRewardState:
    relics: list[RelicSnapshot] = field(default_factory=list)
    source: str | None = None
    sapphire_key_available: bool = False
    linked_relic: RelicSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "relics": [relic.to_dict() for relic in self.relics],
            "source": self.source,
            "sapphire_key_available": self.sapphire_key_available,
            "linked_relic": self.linked_relic.to_dict() if self.linked_relic else None,
        }


@dataclass(slots=True)
class RecommendationContext:
    screen_type: str
    screen_state: dict[str, Any] = field(default_factory=dict)
    card_reward: CardRewardState | None = None
    shop: ShopScreenState | None = None
    relic_reward: RelicRewardState | None = None

    def normalized_state(self) -> dict[str, Any]:
        normalized: dict[str, Any] = {"screen_type": self.screen_type}
        if self.card_reward is not None:
            normalized["card_reward"] = self.card_reward.to_dict()
        if self.shop is not None:
            normalized["shop"] = self.shop.to_dict()
        if self.relic_reward is not None:
            normalized["relic_reward"] = self.relic_reward.to_dict()
        hand = self.screen_state.get("hand")
        monsters = self.screen_state.get("monsters")
        energy = self.screen_state.get("energy")
        if hand is not None or monsters is not None or energy is not None:
            normalized["combat"] = {
                "hand": hand if isinstance(hand, list) else [],
                "monsters": monsters if isinstance(monsters, list) else [],
                "energy": energy,
            }
        return normalized

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_type": self.screen_type,
            "screen_state": self.screen_state,
            "normalized": self.normalized_state(),
        }


@dataclass(slots=True)
class GameSnapshot:
    in_game: bool
    ready_for_command: bool
    available_commands: list[str]
    character_class: str | None
    ascension_level: int | None
    floor: int | None
    act: int | None
    gold: int | None
    current_hp: int | None
    max_hp: int | None
    deck: list[CardSnapshot]
    relics: list[RelicSnapshot]
    context: RecommendationContext
    raw_game_state: dict[str, Any] = field(default_factory=dict, repr=False)

    def deck_breakdown(self) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, int], dict[str, Any]] = {}
        for card in self.deck:
            key = (card.id, card.upgrades)
            bucket = grouped.get(key)
            if bucket is None:
                bucket = {
                    "id": card.id,
                    "name": card.name,
                    "display_name": card.display_name,
                    "copies": 0,
                    "upgrades": card.upgrades,
                    "cost": card.cost,
                    "type": card.type,
                    "rarity": card.rarity,
                    "misc": card.misc,
                }
                grouped[key] = bucket
            bucket["copies"] += 1
        return sorted(grouped.values(), key=lambda item: (item["name"], item["upgrades"]))

    def relic_names(self) -> list[str]:
        return [relic.name for relic in self.relics]

    def to_llm_payload(self) -> dict[str, Any]:
        return {
            "in_game": self.in_game,
            "ready_for_command": self.ready_for_command,
            "available_commands": self.available_commands,
            "character_class": self.character_class,
            "ascension_level": self.ascension_level,
            "floor": self.floor,
            "act": self.act,
            "gold": self.gold,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "screen": {
                "screen_type": self.context.screen_type,
                "screen_state_raw": self.context.screen_state,
                "screen_state_normalized": self.context.normalized_state(),
            },
            "deck_size": len(self.deck),
            "deck": self.deck_breakdown(),
            "relics": [relic.to_dict() for relic in self.relics],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "in_game": self.in_game,
            "ready_for_command": self.ready_for_command,
            "available_commands": self.available_commands,
            "character_class": self.character_class,
            "ascension_level": self.ascension_level,
            "floor": self.floor,
            "act": self.act,
            "gold": self.gold,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "deck_size": len(self.deck),
            "deck": [card.to_dict() for card in self.deck],
            "deck_breakdown": self.deck_breakdown(),
            "relics": [relic.to_dict() for relic in self.relics],
            "screen": self.context.to_dict(),
        }
