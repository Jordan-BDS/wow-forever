#!/usr/bin/env python3
"""
Extrait un petit échantillon des exports wago.tools pour les tests (apps/gamedata/fixtures/wago_sample).

    uv run python scripts/make_wago_sample.py <dossier des CSV complets>

Conserve : les talents du mage, trois objets emblématiques et un set, deux enchantements,
deux recettes d'alchimie, et toutes les lignes de référence nécessaires (sorts, icônes…).
"""

import csv
import sys
from pathlib import Path

SOURCE = Path(sys.argv[1])
TARGET = Path(__file__).resolve().parent.parent / "apps" / "gamedata" / "fixtures" / "wago_sample"
TARGET.mkdir(parents=True, exist_ok=True)

ITEM_IDS = {"19019", "18821", "13262", "16963", "16966", "13446", "13444", "8838", "3372", "7909"}
ITEM_SET_IDS: set[str] = set()  # choisi automatiquement : le premier set dont au moins 3 pièces existent
TALENT_TABS = {"41", "61", "81"}  # Mage
RECIPE_SPELLS = {"17580", "17553"}  # Potion de mana majeure, Potion de mana excellente
ENCHANT_IDS = {"1900", "2505"}  # Croisé, +7 dégâts des sorts (arme)


def rows(table):
    with (SOURCE / f"{table}.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def write(table, fieldnames, selected):
    with (TARGET / f"{table}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected)
    print(f"{table}: {len(selected)}")


def keep(table, predicate):
    fieldnames, data = rows(table)
    selected = [r for r in data if predicate(r)]
    write(table, fieldnames, selected)
    return selected


spells = set()

_, sparse_rows = rows("ItemSparse")
present = {r["ID"] for r in sparse_rows if r["Display_lang"]}
for row in rows("ItemSet")[1]:
    ids = [row[f"ItemID_{i}"] for i in range(17) if row[f"ItemID_{i}"] != "0"]
    if sum(i in present for i in ids) >= 3:
        ITEM_SET_IDS.add(row["ID"])
        ITEM_IDS.update(i for i in ids if i in present)
        print("set choisi :", row["ID"], row["Name_lang"])
        break

talent_tabs = keep("TalentTab", lambda r: r["ID"] in TALENT_TABS)
talents = keep("Talent", lambda r: r["TabID"] in TALENT_TABS)
for t in talents:
    spells.update(t[f"SpellRank_{i}"] for i in range(9) if t[f"SpellRank_{i}"] != "0")

keep("ItemSet", lambda r: r["ID"] in ITEM_SET_IDS)
set_spells = keep("ItemSetSpell", lambda r: r["ItemSetID"] in ITEM_SET_IDS)
spells.update(r["SpellID"] for r in set_spells)

keep("SkillLine", lambda r: True)
keep("SkillLineAbility", lambda r: r["Spell"] in RECIPE_SPELLS)
spells.update(RECIPE_SPELLS)
reagents = keep("SpellReagents", lambda r: r["SpellID"] in RECIPE_SPELLS)
for r in reagents:
    ITEM_IDS.update(r[f"Reagent_{i}"] for i in range(8) if r[f"Reagent_{i}"] != "0")

enchants = keep("SpellItemEnchantment", lambda r: r["ID"] in ENCHANT_IDS)
_, effects = rows("SpellEffect")
enchant_spells = {
    e["SpellID"] for e in effects if e["Effect"] == "53" and e["EffectMiscValue_0"] in ENCHANT_IDS
}
spells.update(enchant_spells)
for r in enchants:  # auras « Équipé : … » portées par les enchantements
    spells.update(
        r[f"EffectArg_{i}"] for i in range(3) if r[f"Effect_{i}"] == "3" and r[f"EffectArg_{i}"] != "0"
    )
keep("SpellEquippedItems", lambda r: r["SpellID"] in enchant_spells)
selected_effects = [e for e in effects if e["SpellID"] in spells]
write("SpellEffect", rows("SpellEffect")[0], selected_effects)
for e in selected_effects:
    if e["Effect"] == "24" and e["EffectItemType"] != "0":
        ITEM_IDS.add(e["EffectItemType"])

keep("SpellName", lambda r: r["ID"] in spells)
keep("Spell", lambda r: r["ID"] in spells)
spell_misc = keep("SpellMisc", lambda r: r.get("SpellID", r["ID"]) in spells)

item_sparse = keep("ItemSparse", lambda r: r["ID"] in ITEM_IDS)
keep("ItemSparse.enUS", lambda r: r["ID"] in ITEM_IDS)
items = keep("Item", lambda r: r["ID"] in ITEM_IDS)
levels = {r["ItemLevel"] for r in item_sparse}
keep("RandPropPoints", lambda r: r["ID"] in levels)

icon_ids = {r["IconFileDataID"] for r in items} | {r["SpellIconFileDataID"] for r in spell_misc}
keep("ManifestInterfaceData", lambda r: r["ID"] in icon_ids)
