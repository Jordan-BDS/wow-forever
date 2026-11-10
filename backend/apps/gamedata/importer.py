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
    "ItemModifiedAppearance",
    "ItemAppearance",
]

# Arbres de talents de Forever : refaits dans le système de traits du client moderne. Tables facultatives
# (absentes d'un client Classic) : sans elles, les talents viennent de la seule table `Talent`.
TRAIT_TABLES = [
    "SkillLineXTraitTree",
    "TraitNode",
    "TraitNodeXTraitNodeEntry",
    "TraitNodeEntry",
    "TraitDefinition",
    "TraitEdge",
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
        icon = self.spell_icons.get(spell_id, "")
        return "" if icon == "temp" else icon


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
    appearance_icon = {
        r["ID"]: data.icons.get(r["DefaultIconFileDataID"], "")
        for r in read(data.directory, "ItemAppearance")
    }
    fallback_icon: dict[str, str] = {}
    for row in read(data.directory, "ItemModifiedAppearance"):
        icon = appearance_icon.get(row["ItemAppearanceID"], "")
        if icon and (row["ItemID"] not in fallback_icon or to_int(row["OrderIndex"]) == 0):
            fallback_icon[row["ItemID"]] = icon

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
                icon=data.icons.get(extra.get("IconFileDataID", ""), "") or fallback_icon.get(row["ID"], ""),
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


# Grille d'un arbre de traits de classe (unités de l'éditeur du client) : trois blocs de quatre colonnes, un
# par arbre de talents dans l'ordre des onglets, case de 600 de côté. Relevé sur le build 1.60.1.70862.
# Un nœud posé à 10 près reste dans sa case ; au-delà de la tolérance, c'est un nœud mort parqué hors grille.
TRAIT_BLOCK_ORIGINS = (1020, 5020, 9080)
TRAIT_TOP = 2130
TRAIT_CELL = 600
TRAIT_COLUMNS = 4
TRAIT_ROWS = 9
TRAIT_TOLERANCE = 100
TRAIT_EDGE_PREREQUISITES = {2, 3}  # TraitEdge.Type : suffisant / requis pour débloquer (0 = décoratif)


def trait_cell(x: int, y: int) -> tuple[int, int, int] | None:
    """(bloc, rangée, colonne) d'un nœud d'après sa position, None s'il est hors de la grille."""
    row = round((y - TRAIT_TOP) / TRAIT_CELL)
    if not 0 <= row < TRAIT_ROWS or abs(y - TRAIT_TOP - row * TRAIT_CELL) > TRAIT_TOLERANCE:
        return None
    for block, origin in enumerate(TRAIT_BLOCK_ORIGINS):
        column = round((x - origin) / TRAIT_CELL)
        if 0 <= column < TRAIT_COLUMNS and abs(x - origin - column * TRAIT_CELL) <= TRAIT_TOLERANCE:
            return block, row, column
    return None


def _classic_talents(data: ClientData, tree_ids: set[int]) -> list[Talent]:
    """Talents de la table `Talent` (arbres Classic)."""
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
        talents.append(
            Talent(
                id=to_int(row["ID"]),
                tree_id=tab_id,
                name=name,
                icon=icon,
                row=to_int(row["TierID"]),
                column=to_int(row["ColumnIndex"]),
                rank_spells=ranks,
                prerequisite_id=to_int(row["PrereqTalent_0"]) or None,
                prerequisite_rank=to_int(row["PrereqRank_0"]),
            )
        )
    return talents


def _trait_talents(
    data: ClientData, trees: list[TalentTree], classic: list[Talent]
) -> dict[int, list[Talent]]:
    """Talents lus dans les arbres de traits, par classe (id de PlayerClass → talents) : case d'après la
    position du nœud, rang max et sort d'après son entrée, prérequis d'après les arêtes. Un talent qui
    existait en Classic (même sort) garde son identifiant, donc sa place dans les builds enregistrés ; un
    talent nouveau prend l'identifiant de son nœud. Les classes sans arbre de traits ne sont pas dans le
    résultat."""
    tabs_by_class: dict[int, list[TalentTree]] = defaultdict(list)
    for tree in sorted(trees, key=lambda t: t.order):
        tabs_by_class[tree.player_class_id].append(tree)
    class_of_tab = {tree.id: tree.player_class_id for tree in trees}
    by_spell: dict[int, tuple[Talent, int]] = {}
    for talent in classic:
        for position, spell_id in enumerate(talent.rank_spells):
            by_spell.setdefault(spell_id, (talent, position))

    definitions = {r["ID"]: r for r in read(data.directory, "TraitDefinition")}
    entries = {r["ID"]: r for r in read(data.directory, "TraitNodeEntry")}
    entry_of_node: dict[str, dict] = {}
    for link in sorted(read(data.directory, "TraitNodeXTraitNodeEntry"), key=lambda r: to_int(r["_Index"])):
        if link["TraitNodeEntryID"] in entries:
            entry_of_node.setdefault(link["TraitNodeID"], entries[link["TraitNodeEntryID"]])
    class_trees = {r["TraitTreeID"] for r in read(data.directory, "SkillLineXTraitTree")}
    nodes_by_tree: dict[str, list[dict]] = defaultdict(list)
    for node in read(data.directory, "TraitNode"):
        if node["TraitTreeID"] in class_trees:
            nodes_by_tree[node["TraitTreeID"]].append(node)

    result: dict[int, list[Talent]] = {}
    talent_of_node: dict[str, Talent] = {}
    for trait_tree, nodes in sorted(nodes_by_tree.items()):
        placed = []
        votes: dict[int, int] = defaultdict(int)
        for node in sorted(nodes, key=lambda n: to_int(n["ID"])):
            cell = trait_cell(to_int(node["PosX"]), to_int(node["PosY"]))
            entry = entry_of_node.get(node["ID"])
            definition = definitions.get(entry["TraitDefinitionID"]) if entry else None
            spell = to_int(definition["SpellID"]) if definition else 0
            if cell is None or not spell:
                logger.warning(
                    "Arbre de traits %s : nœud %s ignoré (position %s, %s ; sort %s)",
                    trait_tree, node["ID"], node["PosX"], node["PosY"], spell,
                )  # fmt: skip
                continue
            placed.append((node, cell, entry, definition, spell))
            if spell in by_spell:
                votes[class_of_tab[by_spell[spell][0].tree_id]] += 1
        if not votes:
            logger.warning("Arbre de traits %s : aucune classe reconnue, ignoré", trait_tree)
            continue
        # La classe de l'arbre : celle dont il reprend le plus de talents Classic.
        class_id = max(votes, key=lambda c: (votes[c], -c))
        tabs = tabs_by_class[class_id]
        talents: list[Talent] = []
        used: set[int] = set()
        cells: set[tuple[int, int, int]] = set()
        for node, cell, entry, definition, spell in placed:
            block, row, column = cell
            if block >= len(tabs) or cell in cells:
                logger.warning("Arbre de traits %s : nœud %s ignoré (case %s)", trait_tree, node["ID"], cell)
                continue
            cells.add(cell)
            max_rank = max(1, to_int(entry["MaxRanks"], 1))
            # Les sorts des rangs suivants ne sont connus que pour un talent Classic ; sinon, et au-delà, le
            # dernier sort connu est répété : la longueur de la liste reste le rang max.
            ranks = [spell]
            talent_id = to_int(node["ID"])
            old = by_spell.get(spell)
            if old and class_of_tab[old[0].tree_id] == class_id:
                ranks = old[0].rank_spells[old[1] : old[1] + max_rank]
                if old[0].id not in used:
                    talent_id = old[0].id
            used.add(talent_id)
            ranks = ranks + [ranks[-1]] * (max_rank - len(ranks))
            name = definition["OverrideName_lang"] or data.spell_names.get(str(spell), "")
            name = name or f"Talent {talent_id}"
            icon = data.icons.get(definition["OverrideIcon"], "") or data.spell_icon(str(spell))
            talent = Talent(
                id=talent_id, tree_id=tabs[block].id, name=name[:80], icon=icon, row=row, column=column,
                rank_spells=ranks, prerequisite_id=None, prerequisite_rank=0,
            )  # fmt: skip
            talents.append(talent)
            talent_of_node[node["ID"]] = talent
        result[class_id] = talents

    for edge in read(data.directory, "TraitEdge"):
        if to_int(edge["Type"]) not in TRAIT_EDGE_PREREQUISITES:
            continue
        required = talent_of_node.get(edge["LeftTraitNodeID"])
        talent = talent_of_node.get(edge["RightTraitNodeID"])
        if required is None or talent is None or required.tree_id != talent.tree_id:
            continue
        if talent.prerequisite_id is None:
            talent.prerequisite_id = required.id  # rang requis 0 : le rang max du prérequis
    return result


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

    talents = _classic_talents(data, tree_ids)
    if has_trait_tables(data.directory):
        # Les classes qui ont un arbre de traits sont lues là : c'est lui que le jeu affiche.
        from_traits = _trait_talents(data, trees, talents)
        class_of_tab = {tree.id: tree.player_class_id for tree in trees}
        talents = [t for t in talents if class_of_tab[t.tree_id] not in from_traits]
        for class_talents in from_traits.values():
            talents.extend(class_talents)
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
    # Les talents que le jeu n'a plus quittent l'index ; les builds enregistrés sont nettoyés après l'import.
    removed, _ = Talent.objects.filter(tree_id__in=tree_ids).exclude(id__in=known).delete()
    return {"talent_trees": tree_count, "talents": count, "talents_removed": removed}


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
    item_icons = dict(Item.objects.values_list("id", "icon"))
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
            icon=data.spell_icon(spell_id) or item_icons.get(product_id or 0, ""),
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


def has_trait_tables(directory: Path) -> bool:
    return all((Path(directory) / f"{table}.csv").exists() for table in TRAIT_TABLES)


@transaction.atomic
def import_directory(directory: Path, build: str = "", product: str = "") -> ImportRun:
    data = ClientData(Path(directory))
    counts = {}
    counts.update(import_items(data))
    counts.update(import_enchantments(data))
    counts.update(import_talents(data))
    counts.update(import_recipes(data))
    # Import tardif : l'app des personnages dépend de celle-ci, pas l'inverse.
    from apps.characters.talent_rules import prune_builds

    counts["talent_builds_pruned"] = prune_builds()
    logger.info("Import %s %s : %s", product, build, counts)
    return ImportRun.objects.create(build=build, product=product, counts=counts)
