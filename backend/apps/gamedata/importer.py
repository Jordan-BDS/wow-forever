"""
Import de l'index du jeu depuis les exports CSV des tables client (wago.tools).

Rejouable et idempotent : chaque table est écrasée par clé primaire (bulk upsert), et les
lignes marquées `is_forever` (ajouts manuels) ne sont jamais touchées.
"""

import csv
import logging
from collections import defaultdict
from pathlib import Path

from django.db import transaction

from .models import (
    Enchantment,
    ImportRun,
    Item,
    ItemSet,
    PlayerClass,
    Profession,
    Recipe,
    Talent,
    TalentTree,
)
from .stats import (
    CLASS_MASK_SLUGS,
    QUALITY_COLUMN,
    RAND_PROP_COLUMN,
    SKILL_LINE_PROFESSIONS,
    STAT_TYPES,
)

logger = logging.getLogger(__name__)

TABLES = [
    "ItemSparse",
    "ItemSparse.enUS",
    "Item",
    "ItemSet",
    "ItemSetSpell",
    "RandPropPoints",
    "SpellItemEnchantment",
    "SpellEquippedItems",
    "SpellName",
    "Spell",
    "SpellMisc",
    "SpellEffect",
    "SpellReagents",
    "SkillLine",
    "SkillLineAbility",
    "Talent",
    "TalentTab",
    "ManifestInterfaceData",
]

EFFECT_CREATE_ITEM = 24
EFFECT_ENCHANT_ITEM = 53
ENCHANT_EFFECT_STAT = 5
ENCHANT_EFFECT_RESISTANCE = 4
RESISTANCE_SCHOOLS = {2: 53, 3: 51, 4: 55, 5: 52, 6: 54, 7: 56}  # école → type de stat


def read(directory: Path, table: str) -> list[dict]:
    path = directory / f"{table}.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def to_int(value: str | None, default: int = 0) -> int:
    try:
        return int(float(value)) if value not in (None, "") else default
    except ValueError:
        return default


def upsert(model, objects: list, fields: list[str]) -> int:
    if not objects:
        return 0
    model.objects.bulk_create(objects, update_conflicts=True, update_fields=fields, unique_fields=["id"])
    return len(objects)


class ClientData:
    """Charge les tables une fois et expose les index utiles."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.icons = self._load_icons()
        self.spell_names = {r["ID"]: r["Name_lang"] for r in read(self.directory, "SpellName")}
        self.spell_descriptions = {r["ID"]: r["Description_lang"] for r in read(self.directory, "Spell")}
        self.spell_icons = {
            r.get("SpellID", r["ID"]): self.icons.get(r["SpellIconFileDataID"], "")
            for r in read(self.directory, "SpellMisc")
        }
        self.effects = defaultdict(list)
        for row in read(self.directory, "SpellEffect"):
            self.effects[row["SpellID"]].append(row)
        self.rand_prop = {r["ID"]: r for r in read(self.directory, "RandPropPoints")}

    def _load_icons(self) -> dict[str, str]:
        icons = {}
        for row in read(self.directory, "ManifestInterfaceData"):
            if row["FilePath"].lower().replace("/", "\\") == "interface\\icons\\":
                icons[row["ID"]] = row["FileName"].rsplit(".", 1)[0].lower()
        return icons

    def spell_icon(self, spell_id: str) -> str:
        return self.spell_icons.get(spell_id, "")


# --- objets -------------------------------------------------------------------


def item_stats(row: dict, rand_prop: dict) -> dict[str, int]:
    """Convertit les « pourcentages de budget » du client en valeurs entières."""
    quality = to_int(row["OverallQualityID"])
    column = RAND_PROP_COLUMN.get(to_int(row["InventoryType"]))
    budget_row = rand_prop.get(row["ItemLevel"])
    if column is None or budget_row is None or quality not in QUALITY_COLUMN:
        return {}
    budget = to_int(budget_row[f"{QUALITY_COLUMN[quality]}_{column}"])
    stats = {}
    for index in range(10):
        stat_type = to_int(row[f"StatModifier_bonusStat_{index}"], -1)
        percent = to_int(row[f"StatPercentEditor_{index}"])
        if stat_type < 0 or percent == 0:
            continue
        name = STAT_TYPES.get(stat_type, f"stat_{stat_type}")
        stats[name] = stats.get(name, 0) + round(percent * budget / 10000)
    return stats


def import_items(data: ClientData) -> dict[str, int]:
    english = {r["ID"]: r["Display_lang"] for r in read(data.directory, "ItemSparse.enUS")}
    base = {r["ID"]: r for r in read(data.directory, "Item")}

    sets = []
    set_bonuses = defaultdict(list)
    for row in read(data.directory, "ItemSetSpell"):
        set_bonuses[row["ItemSetID"]].append(
            {
                "threshold": to_int(row["Threshold"]),
                "spell_id": to_int(row["SpellID"]),
                "description": data.spell_descriptions.get(row["SpellID"], ""),
            }
        )
    for row in read(data.directory, "ItemSet"):
        bonuses = sorted(set_bonuses.get(row["ID"], []), key=lambda b: b["threshold"])
        sets.append(ItemSet(id=to_int(row["ID"]), name=row["Name_lang"], bonuses=bonuses))
    set_count = upsert(ItemSet, sets, ["name", "bonuses"])
    known_sets = {s.id for s in sets}

    protected = set(Item.objects.filter(is_forever=True).values_list("id", flat=True))
    items = []
    for row in read(data.directory, "ItemSparse"):
        item_id = to_int(row["ID"])
        if item_id in protected or not row["Display_lang"]:
            continue
        extra = base.get(row["ID"], {})
        set_id = to_int(row["ItemSet"])
        items.append(
            Item(
                id=item_id,
                name=row["Display_lang"],
                name_en=english.get(row["ID"], ""),
                quality=to_int(row["OverallQualityID"]),
                item_level=to_int(row["ItemLevel"], 1),
                required_level=to_int(row["RequiredLevel"]),
                inventory_type=to_int(row["InventoryType"]),
                class_id=to_int(extra.get("ClassID")),
                subclass_id=to_int(extra.get("SubclassID")),
                allowable_class=to_int(row["AllowableClass"], -1),
                is_unique=to_int(row["MaxCount"]) == 1,
                item_set_id=set_id if set_id in known_sets else None,
                icon=data.icons.get(extra.get("IconFileDataID", ""), ""),
                stats=item_stats(row, data.rand_prop),
                description=row["Description_lang"][:255],
            )
        )
    fields = [
        "name", "name_en", "quality", "item_level", "required_level", "inventory_type", "class_id",
        "subclass_id", "allowable_class", "is_unique", "item_set", "icon", "stats", "description",
    ]  # fmt: skip
    count = 0
    for start in range(0, len(items), 2000):
        count += upsert(Item, items[start : start + 2000], fields)
    return {"items": count, "item_sets": set_count}


# --- enchantements ----------------------------------------------------------------

ENCHANT_EFFECT_EQUIP_SPELL = 3
AURA_STAT = {135: "spell_healing", 99: "attack_power", 124: "ranged_attack_power", 85: "mana_regen"}
AURA_PRIMARY_STATS = ["strength", "agility", "stamina", "intellect", "spirit"]
SCHOOL_RESISTANCE = {2: "holy_resistance", 4: "fire_resistance", 8: "nature_resistance",
                     16: "frost_resistance", 32: "shadow_resistance", 64: "arcane_resistance"}  # fmt: skip


def aura_stats(data: "ClientData", spell_id: str) -> dict[str, int]:
    """Stats simples portées par les auras d'un sort (bonus plats seulement)."""
    stats: dict[str, int] = {}

    def add(name: str, value: int) -> None:
        if value:
            stats[name] = stats.get(name, 0) + value

    for effect in data.effects.get(spell_id, []):
        aura, points, misc = (
            to_int(effect["EffectAura"]),
            to_int(effect["EffectBasePointsF"]),
            to_int(effect["EffectMiscValue_0"]),
        )
        if aura in AURA_STAT:
            add(AURA_STAT[aura], points)
        elif aura == 13 and misc & 126 == 126:  # dégâts des sorts, toutes écoles
            add("spell_damage", points)
        elif aura == 29:  # caractéristique
            for index, name in enumerate(AURA_PRIMARY_STATS):
                if misc == -1 or misc == index:
                    add(name, points)
        elif aura == 22:  # résistances
            for bit, name in SCHOOL_RESISTANCE.items():
                if misc & bit:
                    add(name, points)
    return stats


def import_enchantments(data: ClientData) -> dict[str, int]:
    applying_spell = {}
    for spell_id, effects in data.effects.items():
        for effect in effects:
            if to_int(effect["Effect"]) == EFFECT_ENCHANT_ITEM:
                applying_spell.setdefault(effect["EffectMiscValue_0"], spell_id)
    equipped = {row["SpellID"]: row for row in read(data.directory, "SpellEquippedItems")}

    enchants = []
    for row in read(data.directory, "SpellItemEnchantment"):
        spell_id = applying_spell.get(row["ID"])
        if not spell_id or not row["Name_lang"]:
            continue
        stats: dict[str, int] = {}
        for index in range(3):
            effect = to_int(row[f"Effect_{index}"])
            points = to_int(row[f"EffectPointsMin_{index}"])
            arg = to_int(row[f"EffectArg_{index}"])
            if effect == ENCHANT_EFFECT_STAT and points:
                name = STAT_TYPES.get(arg, f"stat_{arg}")
                stats[name] = stats.get(name, 0) + points
            elif effect == ENCHANT_EFFECT_RESISTANCE and points and arg in RESISTANCE_SCHOOLS:
                name = STAT_TYPES[RESISTANCE_SCHOOLS[arg]]
                stats[name] = stats.get(name, 0) + points
            elif effect == ENCHANT_EFFECT_EQUIP_SPELL and arg:
                for name, value in aura_stats(data, str(arg)).items():
                    stats[name] = stats.get(name, 0) + value
        enchants.append(
            Enchantment(
                id=to_int(row["ID"]),
                name=row["Name_lang"],
                spell_id=to_int(spell_id),
                icon=data.spell_icon(spell_id),
                stats=stats,
                slot_mask=to_int(equipped.get(spell_id, {}).get("EquippedItemInvTypes")),
                equipped_class=to_int(equipped.get(spell_id, {}).get("EquippedItemClass"), -1),
                equipped_subclass_mask=to_int(equipped.get(spell_id, {}).get("EquippedItemSubclass")),
                required_skill=to_int(row["RequiredSkillID"]),
                required_skill_rank=to_int(row["RequiredSkillRank"]),
            )
        )
    fields = [
        "name", "spell_id", "icon", "stats", "slot_mask", "equipped_class", "equipped_subclass_mask",
        "required_skill", "required_skill_rank",
    ]  # fmt: skip
    return {"enchantments": upsert(Enchantment, enchants, fields)}


# --- talents ------------------------------------------------------------------------


def import_talents(data: ClientData) -> dict[str, int]:
    classes = {c.slug: c for c in PlayerClass.objects.all()}
    trees = []
    for row in read(data.directory, "TalentTab"):
        slug = CLASS_MASK_SLUGS.get(to_int(row["ClassMask"]))
        if slug not in classes:
            continue
        trees.append(
            TalentTree(
                id=to_int(row["ID"]),
                player_class=classes[slug],
                name=row["Name_lang"],
                background=row["BackgroundFile"],
                order=to_int(row["OrderIndex"]),
            )
        )
    tree_count = upsert(TalentTree, trees, ["player_class", "name", "background", "order"])
    tree_ids = {t.id for t in trees}

    talents = []
    for row in read(data.directory, "Talent"):
        tab_id = to_int(row["TabID"])
        if tab_id not in tree_ids:
            continue
        ranks = [to_int(row[f"SpellRank_{i}"]) for i in range(9)]
        ranks = [r for r in ranks if r]
        if not ranks:
            continue
        # Nom et icône : premier rang dont le sort est connu (certains sorts manquent dans les exports).
        name = next(
            (data.spell_names[str(r)] for r in ranks if data.spell_names.get(str(r))), f"Talent {row['ID']}"
        )
        icon = next((data.spell_icon(str(r)) for r in ranks if data.spell_icon(str(r))), "")
        prerequisite = to_int(row["PrereqTalent_0"]) or None
        talents.append(
            Talent(
                id=to_int(row["ID"]),
                tree_id=tab_id,
                name=name,
                icon=icon,
                row=to_int(row["TierID"]),
                column=to_int(row["ColumnIndex"]),
                rank_spells=ranks,
                prerequisite_id=prerequisite,
                prerequisite_rank=to_int(row["PrereqRank_0"]),
            )
        )
    known = {t.id for t in talents}
    for talent in talents:
        if talent.prerequisite_id not in known:
            talent.prerequisite_id = None
            talent.prerequisite_rank = 0
    # Deux passes : les prérequis pointent vers des talents du même import.
    fields = ["tree", "name", "icon", "row", "column", "rank_spells", "prerequisite", "prerequisite_rank"]
    for talent in talents:
        talent._prereq = talent.prerequisite_id
        talent.prerequisite_id = None
    count = upsert(Talent, talents, fields)
    for talent in talents:
        talent.prerequisite_id = talent._prereq
    upsert(Talent, [t for t in talents if t.prerequisite_id], ["prerequisite", "prerequisite_rank"])
    return {"talent_trees": tree_count, "talents": count}


# --- recettes -----------------------------------------------------------------------


def estimate_min_skill(yellow: int) -> int:
    """
    Le client ne stocke que les paliers jaune (TrivialSkillLineRankLow) et gris. Le niveau requis
    (orange) en est déduit : écart de 15 en haut niveau, plus large en bas (vérifié sur l'alchimie).
    """
    if yellow <= 60:
        return 1
    if yellow < 100:
        return yellow - 30
    if yellow < 225:
        return yellow - 25
    return yellow - 15


def import_recipes(data: ClientData) -> dict[str, int]:
    professions = {p.slug: p for p in Profession.objects.all()}
    parent_of = {}
    for row in read(data.directory, "SkillLine"):
        parent_of[row["ID"]] = row["ParentSkillLineID"] if to_int(row["ParentSkillLineID"]) else row["ID"]
    reagents_by_spell = {}
    for row in read(data.directory, "SpellReagents"):
        reagents_by_spell[row["SpellID"]] = [
            {"item_id": to_int(row[f"Reagent_{i}"]), "count": to_int(row[f"ReagentCount_{i}"])}
            for i in range(8)
            if to_int(row[f"Reagent_{i}"])
        ]
    item_names = dict(Item.objects.values_list("id", "name"))
    protected = set(Recipe.objects.filter(is_forever=True).values_list("id", flat=True))

    recipes = {}
    for row in read(data.directory, "SkillLineAbility"):
        skill_line = parent_of.get(row["SkillLine"], row["SkillLine"])
        slug = SKILL_LINE_PROFESSIONS.get(to_int(skill_line))
        spell_id = row["Spell"]
        if slug not in professions or to_int(spell_id) in protected or spell_id in recipes:
            continue
        product_id, quantity = None, 1
        for effect in data.effects.get(spell_id, []):
            if to_int(effect["Effect"]) == EFFECT_CREATE_ITEM and to_int(effect["EffectItemType"]):
                product_id = to_int(effect["EffectItemType"])
                quantity = max(1, to_int(effect["EffectBasePointsF"]))
                break
        if product_id is None and slug not in ("enchanting",):
            continue  # pas une recette de fabrication (compétence passive, apprentissage…)
        name = data.spell_names.get(spell_id) or item_names.get(product_id or 0, "")
        if not name:
            continue
        reagents = [
            {**reagent, "name": item_names.get(reagent["item_id"], "")}
            for reagent in reagents_by_spell.get(spell_id, [])
        ]
        recipes[spell_id] = Recipe(
            id=to_int(spell_id),
            profession=professions[slug],
            name=name,
            icon=data.spell_icon(spell_id),
            min_skill=estimate_min_skill(to_int(row["TrivialSkillLineRankLow"])),
            skill_yellow=to_int(row["TrivialSkillLineRankLow"]),
            skill_grey=to_int(row["TrivialSkillLineRankHigh"]),
            product_id=product_id if product_id in item_names else None,
            quantity=quantity,
            reagents=reagents,
            acquire_method=to_int(row["AcquireMethod"]),
        )
    fields = [
        "profession", "name", "icon", "min_skill", "skill_yellow", "skill_grey", "product", "quantity",
        "reagents", "acquire_method",
    ]  # fmt: skip
    return {"recipes": upsert(Recipe, list(recipes.values()), fields)}


# --- orchestration ------------------------------------------------------------------


def missing_tables(directory: Path) -> list[str]:
    return [table for table in TABLES if not (Path(directory) / f"{table}.csv").exists()]


@transaction.atomic
def import_directory(directory: Path, build: str = "", product: str = "") -> ImportRun:
    data = ClientData(Path(directory))
    counts = {}
    counts.update(import_items(data))
    counts.update(import_enchantments(data))
    counts.update(import_talents(data))
    counts.update(import_recipes(data))
    logger.info("Import %s %s : %s", product, build, counts)
    return ImportRun.objects.create(build=build, product=product, counts=counts)
