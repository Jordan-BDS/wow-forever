"""
Moteur de statistiques (MVP) : somme des stats brutes de l'équipement acquis, des
    enchantements et des bonus de set.

Conçu en « sources » additionnables : chaque source renvoie {stat: valeur}. Les stats dérivées, les talents et
les buffs viendront s'ajouter comme nouvelles sources (cf. cahier des charges § 4).
"""

from collections import defaultdict
from dataclasses import dataclass, field

from apps.gamedata.models import Enchantment, Item

STAT_ORDER = [
    "strength",
    "agility",
    "stamina",
    "intellect",
    "spirit",
    "attack_power",
    "ranged_attack_power",
    "spell_damage",
    "spell_healing",
    "spell_power",
    "mana_regen",
    "crit_rating",
    "hit_rating",
    "defense_rating",
    "dodge_rating",
    "parry_rating",
    "block_rating",
    "block_value",
    "bonus_armor",
    "fire_resistance",
    "frost_resistance",
    "nature_resistance",
    "shadow_resistance",
    "arcane_resistance",
    "holy_resistance",
]


@dataclass
class SlotInput:
    slot: str
    item: Item | None
    enchantment: Enchantment | None = None
    projected: bool = False


@dataclass
class StatsResult:
    totals: dict[str, int] = field(default_factory=dict)
    breakdown: dict[str, dict[str, int]] = field(default_factory=dict)  # stat → {items, enchantments}
    active_set_bonuses: list[dict] = field(default_factory=list)
    inactive_set_bonuses: list[dict] = field(default_factory=list)
    projected_slots: list[str] = field(default_factory=list)


def compute(slots: list[SlotInput]) -> StatsResult:
    result = StatsResult()
    sources: dict[str, dict[str, int]] = {"items": defaultdict(int), "enchantments": defaultdict(int)}
    set_pieces: dict[int, int] = defaultdict(int)
    set_objects = {}

    for entry in slots:
        if entry.item is None:
            continue
        if entry.projected:
            result.projected_slots.append(entry.slot)
            continue
        for stat, value in (entry.item.stats or {}).items():
            sources["items"][stat] += value
        if entry.enchantment:
            for stat, value in (entry.enchantment.stats or {}).items():
                sources["enchantments"][stat] += value
        if entry.item.item_set_id:
            set_pieces[entry.item.item_set_id] += 1
            set_objects[entry.item.item_set_id] = entry.item.item_set

    for set_id, count in set_pieces.items():
        item_set = set_objects[set_id]
        for bonus in item_set.bonuses:
            entry = {
                "set": item_set.name,
                "threshold": bonus["threshold"],
                "spell_id": bonus["spell_id"],
                "description": bonus.get("description", ""),
                "pieces": count,
            }
            (
                result.active_set_bonuses if count >= bonus["threshold"] else result.inactive_set_bonuses
            ).append(entry)

    stats = {stat for source in sources.values() for stat in source}
    for stat in sorted(stats, key=lambda s: (STAT_ORDER.index(s) if s in STAT_ORDER else 99, s)):
        parts = {name: source[stat] for name, source in sources.items() if source[stat]}
        result.breakdown[stat] = parts
        result.totals[stat] = sum(parts.values())
    return result
