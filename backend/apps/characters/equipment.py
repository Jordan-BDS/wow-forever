"""Règles d'équipement vanilla : emplacements, types d'armure et d'armes par classe, unicité."""

from apps.gamedata.models import Enchantment, Item

# Emplacement de la fiche → InventoryType acceptés.
SLOT_INVENTORY_TYPES: dict[str, set[int]] = {
    "head": {1},
    "neck": {2},
    "shoulder": {3},
    "shirt": {4},
    "chest": {5, 20},
    "waist": {6},
    "legs": {7},
    "feet": {8},
    "wrist": {9},
    "hands": {10},
    "finger1": {11},
    "finger2": {11},
    "trinket1": {12},
    "trinket2": {12},
    "back": {16},
    "tabard": {19},
    "main_hand": {13, 17, 21},
    "off_hand": {13, 14, 22, 23},
    "ranged": {15, 25, 26, 28},
}
SLOTS = list(SLOT_INVENTORY_TYPES)
TWO_HAND = 17
PAIRED_SLOTS = {"finger1": "finger2", "finger2": "finger1", "trinket1": "trinket2", "trinket2": "trinket1"}

# ItemClass 4 (armure) : sous-classes 1 tissu, 2 cuir, 3 mailles, 4 plaques,
# 6 bouclier ; 0 = divers (bijoux…).
ARMOR_BY_CLASS: dict[str, set[int]] = {
    "mage": {0, 1},
    "priest": {0, 1},
    "warlock": {0, 1},
    "rogue": {0, 1, 2},
    "druid": {0, 1, 2},
    "hunter": {0, 1, 2, 3},
    "shaman": {0, 1, 2, 3, 6},
    "warrior": {0, 1, 2, 3, 4, 6},
    "paladin": {0, 1, 2, 3, 4, 6},
}

# ItemClass 2 (armes) : 0 hache 1M, 1 hache 2M, 2 arc, 3 arme à feu, 4 masse 1M,
# 5 masse 2M, 6 arme d'hast,
# 7 épée 1M, 8 épée 2M, 10 bâton, 13 arme de pugilat, 15 dague, 16 arme de jet, 18 arbalète,
# 19 baguette, 20 canne à pêche.
WEAPONS_BY_CLASS: dict[str, set[int]] = {
    "warrior": {0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 16, 18, 20},
    "paladin": {0, 1, 4, 5, 6, 7, 8, 20},
    "hunter": {0, 1, 2, 3, 6, 7, 8, 10, 13, 15, 16, 18, 20},
    "rogue": {0, 2, 3, 4, 7, 13, 15, 16, 18, 20},
    "priest": {4, 10, 15, 19, 20},
    "shaman": {0, 1, 4, 5, 10, 13, 15, 20},
    "mage": {7, 10, 15, 19, 20},
    "warlock": {7, 10, 15, 19, 20},
    "druid": {4, 5, 10, 13, 15, 20},
}

# ChrClasses.ID par slug, pour le masque AllowableClass.
CLASS_IDS = {
    "warrior": 1,
    "paladin": 2,
    "hunter": 3,
    "rogue": 4,
    "priest": 5,
    "shaman": 7,
    "mage": 8,
    "warlock": 9,
    "druid": 11,
}


def item_error(item: Item, slot: str, class_slug: str) -> str | None:
    """Message d'erreur si l'objet ne peut pas aller dans cet emplacement pour cette classe, sinon None."""
    if slot not in SLOT_INVENTORY_TYPES:
        return "Emplacement inconnu."
    if item.inventory_type not in SLOT_INVENTORY_TYPES[slot]:
        return f"{item.name} ne va pas dans cet emplacement."
    if item.allowable_class not in (-1, 0) and not item.allowable_class & (1 << (CLASS_IDS[class_slug] - 1)):
        return f"{item.name} est réservé à d'autres classes."
    if item.class_id == 4 and item.subclass_id not in ARMOR_BY_CLASS.get(class_slug, set()):
        return f"Cette classe ne peut pas porter {item.name} (type d'armure)."
    if item.class_id == 2 and item.subclass_id not in WEAPONS_BY_CLASS.get(class_slug, set()):
        return f"Cette classe ne peut pas manier {item.name} (type d'arme)."
    return None


def enchantment_error(enchantment: Enchantment, item: Item) -> str | None:
    if enchantment.slot_mask and not enchantment.slot_mask & (1 << item.inventory_type):
        return f"{enchantment.name} ne s'applique pas à cet emplacement."
    if enchantment.equipped_class not in (-1, 0) and enchantment.equipped_class != item.class_id:
        return f"{enchantment.name} ne s'applique pas à ce type d'objet."
    if (
        enchantment.equipped_subclass_mask
        and enchantment.equipped_class == item.class_id
        and not enchantment.equipped_subclass_mask & (1 << item.subclass_id)
    ):
        return f"{enchantment.name} ne s'applique pas à ce type d'objet."
    return None


def set_errors(slots: dict[str, Item | None]) -> dict[str, str]:
    """Contrôles croisés entre emplacements : arme à deux mains, objets uniques."""
    errors: dict[str, str] = {}
    main_hand, off_hand = slots.get("main_hand"), slots.get("off_hand")
    if main_hand and main_hand.inventory_type == TWO_HAND and off_hand:
        errors["off_hand"] = "Main gauche impossible avec une arme à deux mains."
    for slot, other in PAIRED_SLOTS.items():
        item, twin = slots.get(slot), slots.get(other)
        if item and twin and item.pk == twin.pk and item.is_unique and slot < other:
            errors[other] = f"{item.name} est unique, impossible de l'équiper deux fois."
    return errors
