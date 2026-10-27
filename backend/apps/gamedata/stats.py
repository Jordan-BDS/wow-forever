"""Constantes du jeu : types de stats des objets, emplacements, masques de classes."""

# ItemModType (vanilla). Les « ratings » restent bruts, le moteur de stats les convertira.
STAT_TYPES = {
    0: "mana",
    1: "health",
    3: "agility",
    4: "strength",
    5: "intellect",
    6: "spirit",
    7: "stamina",
    12: "defense_rating",
    13: "dodge_rating",
    14: "parry_rating",
    15: "block_rating",
    16: "hit_melee_rating",
    17: "hit_ranged_rating",
    18: "hit_spell_rating",
    19: "crit_melee_rating",
    20: "crit_ranged_rating",
    21: "crit_spell_rating",
    31: "hit_rating",
    32: "crit_rating",
    38: "attack_power",
    39: "ranged_attack_power",
    41: "spell_healing",
    42: "spell_damage",
    43: "mana_regen",
    45: "spell_power",
    46: "health_regen",
    47: "spell_penetration",
    48: "block_value",
    50: "bonus_armor",
    51: "fire_resistance",
    52: "frost_resistance",
    53: "holy_resistance",
    54: "shadow_resistance",
    55: "nature_resistance",
    56: "arcane_resistance",
}

# InventoryType → emplacement de la fiche de personnage (cf. cahier des charges § 4).
INVENTORY_TYPES = {
    1: "head",
    2: "neck",
    3: "shoulder",
    4: "shirt",
    5: "chest",
    6: "waist",
    7: "legs",
    8: "feet",
    9: "wrist",
    10: "hands",
    11: "finger",
    12: "trinket",
    13: "one_hand",
    14: "shield",
    15: "ranged",
    16: "back",
    17: "two_hand",
    19: "tabard",
    20: "chest",  # robe
    21: "main_hand",
    22: "off_hand",
    23: "held_off_hand",
    25: "thrown",
    26: "ranged",  # armes à feu / arbalètes / baguettes
    28: "relic",
}

# Colonne de RandPropPoints selon l'emplacement (même découpage que le client).
RAND_PROP_COLUMN = {
    1: 0, 5: 0, 7: 0, 17: 0, 20: 0,
    3: 1, 6: 1, 8: 1, 10: 1, 12: 1,
    2: 2, 9: 2, 11: 2, 14: 2, 16: 2, 23: 2,
    13: 3, 21: 3, 22: 3,
    15: 4, 25: 4, 26: 4, 28: 4,
}  # fmt: skip

QUALITY_COLUMN = {2: "Good", 3: "Superior", 4: "Epic", 5: "Epic"}

# Bit de ClassMask → slug de classe (ChrClasses.ID : 1 guerrier … 11 druide).
CLASS_MASK_SLUGS = {
    1: "warrior",
    2: "paladin",
    4: "hunter",
    8: "rogue",
    16: "priest",
    64: "shaman",
    128: "mage",
    256: "warlock",
    1024: "druid",
}

# SkillLine.ID → slug de métier.
SKILL_LINE_PROFESSIONS = {
    171: "alchemy",
    164: "blacksmithing",
    333: "enchanting",
    202: "engineering",
    182: "herbalism",
    165: "leatherworking",
    186: "mining",
    393: "skinning",
    197: "tailoring",
    185: "cooking",
    129: "first-aid",
    356: "fishing",
}

ICON_CDN = "https://wow.zamimg.com/images/wow/icons/large/{icon}.jpg"


def icon_url(icon: str) -> str:
    return ICON_CDN.format(icon=icon or "inv_misc_questionmark")
