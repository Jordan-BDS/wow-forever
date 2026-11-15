"""
Types d'objets de l'hôtel des ventes, rangés comme dans celui du jeu : une catégorie (Armes, Armures…), ses
sous-catégories (Épées à une main, Tissu…) et, pour les armures, l'emplacement (Tête, Torse…).

Un objet est rangé d'après ce que l'index du site en sait : classe, sous-classe et emplacement du client
(`Item.class_id`, `subclass_id`, `inventory_type`). « Divers » prend toutes les classes qu'aucune autre
catégorie ne nomme. Un objet absent de l'index n'est dans aucune catégorie.

La clé d'une catégorie est stable (« weapon », « armor.1 », « armor.1.head ») : la page la renvoie telle
quelle.
"""

from collections.abc import Callable

Kind = tuple[int, int, int]  # classe, sous-classe, emplacement
Test = Callable[[Kind], bool]

CONSUMABLE, CONTAINER, WEAPON, ARMOR, REAGENT, PROJECTILE, TRADE_GOODS, RECIPE, QUIVER, MISC = (
    0, 1, 2, 4, 5, 6, 7, 9, 11, 15,
)  # fmt: skip
NAMED_CLASSES = {CONSUMABLE, CONTAINER, WEAPON, ARMOR, REAGENT, PROJECTILE, TRADE_GOODS, RECIPE, QUIVER}

# Emplacements proposés sous une sous-catégorie d'armure : clé, nom, InventoryType du client.
SLOTS: dict[str, tuple[str, frozenset[int]]] = {
    "head": ("Tête", frozenset({1})),
    "neck": ("Cou", frozenset({2})),
    "shoulder": ("Épaules", frozenset({3})),
    "shirt": ("Chemise", frozenset({4})),
    "chest": ("Torse", frozenset({5, 20})),  # 20 : robe
    "waist": ("Taille", frozenset({6})),
    "legs": ("Jambes", frozenset({7})),
    "feet": ("Pieds", frozenset({8})),
    "wrist": ("Poignets", frozenset({9})),
    "hands": ("Mains", frozenset({10})),
    "finger": ("Doigt", frozenset({11})),
    "trinket": ("Bijou", frozenset({12})),
    "back": ("Dos", frozenset({16})),
    "tabard": ("Tabard", frozenset({19})),
    "held": ("Tenu en main gauche", frozenset({23})),
}
BODY = ["head", "shoulder", "chest", "wrist", "hands", "waist", "legs", "feet"]


def _node(key: str, label: str, test: Test, children: list[dict] | None = None) -> dict:
    return {"key": key, "label": label, "test": test, "children": children or []}


def _class(key: str, label: str, class_id: int, subclasses=(), slots: dict[int, list[str]] | None = None):
    """Une catégorie d'une classe du client, ses sous-classes nommées et, pour certaines, leurs emplacements.
    Les sous-classes sans nom ici restent dans la catégorie, sans sous-catégorie à elles."""
    children = []
    for subclass_id, name in subclasses:
        below = [
            _node(
                f"{key}.{subclass_id}.{slot}",
                SLOTS[slot][0],
                lambda kind, s=subclass_id, types=SLOTS[slot][1]: (
                    kind[0] == class_id and kind[1] == s and kind[2] in types
                ),
            )
            for slot in (slots or {}).get(subclass_id, [])
        ]
        children.append(
            _node(
                f"{key}.{subclass_id}",
                name,
                lambda kind, s=subclass_id: kind[0] == class_id and kind[1] == s,
                below,
            )
        )
    return _node(key, label, lambda kind: kind[0] == class_id, children)


CATEGORIES: list[dict] = [
    _class(
        "weapon", "Armes", WEAPON,
        [
            (0, "Haches à une main"), (1, "Haches à deux mains"), (2, "Arcs"), (3, "Armes à feu"),
            (4, "Masses à une main"), (5, "Masses à deux mains"), (6, "Armes d'hast"),
            (7, "Épées à une main"), (8, "Épées à deux mains"), (10, "Bâtons"), (13, "Armes de pugilat"),
            (14, "Divers"), (15, "Dagues"), (16, "Armes de jet"), (18, "Arbalètes"), (19, "Baguettes"),
            (20, "Cannes à pêche"),
        ],
    ),
    _class(
        "armor", "Armures", ARMOR,
        [
            (0, "Divers"), (1, "Tissu"), (2, "Cuir"), (3, "Mailles"), (4, "Plaques"), (6, "Boucliers"),
            (7, "Librams"), (8, "Idoles"), (9, "Totems"),
        ],
        slots={
            0: ["head", "neck", "shirt", "finger", "trinket", "held", "tabard"],
            1: [*BODY, "back"],
            2: BODY,
            3: BODY,
            4: BODY,
        },
    ),
    _class(
        "container", "Conteneurs", CONTAINER,
        [(0, "Sacs"), (1, "Sacs d'âme"), (2, "Sacs d'herbes"), (3, "Sacs d'enchanteur")],
    ),
    _class(
        "consumable", "Consommables", CONSUMABLE,
        [
            (5, "Nourriture et boissons"), (1, "Potions"), (2, "Élixirs"), (3, "Flacons"), (4, "Parchemins"),
            (7, "Bandages"), (6, "Améliorations d'objet"), (0, "Explosifs et appareils"), (8, "Autres"),
        ],
    ),
    _class(
        "trade", "Artisanat", TRADE_GOODS,
        [
            (5, "Tissu"), (6, "Cuir"), (7, "Métal et pierre"), (8, "Viande"), (9, "Herbes"),
            (10, "Élémentaire"), (12, "Enchantement"), (1, "Pièces détachées"), (2, "Explosifs"),
            (3, "Appareils"), (11, "Autres"),
        ],
    ),
    _class("projectile", "Projectiles", PROJECTILE, [(2, "Flèches"), (3, "Balles")]),
    _class("quiver", "Carquois", QUIVER, [(2, "Carquois"), (3, "Gibernes")]),
    _class(
        "recipe", "Recettes", RECIPE,
        [
            (0, "Livres"), (1, "Travail du cuir"), (2, "Couture"), (3, "Ingénierie"), (4, "Forge"),
            (5, "Cuisine"), (6, "Alchimie"), (7, "Secourisme"), (8, "Enchantement"), (9, "Pêche"),
        ],
    ),
    _class("reagent", "Réactifs", REAGENT),
    _node(
        "misc", "Divers", lambda kind: kind[0] not in NAMED_CLASSES,
        [
            _node(f"misc.{subclass_id}", name, lambda kind, s=subclass_id: kind[0] == MISC and kind[1] == s)
            for subclass_id, name in [(0, "Camelote"), (2, "Mascottes"), (3, "Fêtes"), (5, "Montures")]
        ],
    ),
]  # fmt: skip


def _flatten(nodes: list[dict]) -> dict[str, Test]:
    found = {}
    for node in nodes:
        found[node["key"]] = node["test"]
        found.update(_flatten(node["children"]))
    return found


TESTS = _flatten(CATEGORIES)


def test_for(key: str) -> Test | None:
    """Ce qui dit si un objet est dans la catégorie `key`. None si la clé n'est pas celle d'une catégorie."""
    return TESTS.get(key)


def tree(nodes: list[dict] | None = None) -> list[dict]:
    """L'arbre des catégories pour la page : clé, nom, sous-catégories."""
    nodes = CATEGORIES if nodes is None else nodes
    return [{"key": n["key"], "label": n["label"], "children": tree(n["children"])} for n in nodes]
