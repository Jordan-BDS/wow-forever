"""
Données vanilla (Classic Era) pré-remplies, plus la race Skyborn de WoW Forever.
`seed()` est idempotent : rejouable sans dupliquer, met à jour noms et couleurs,
ne supprime jamais rien (les ajouts faits via l'admin survivent).
"""

from .models import Instance, PlayerClass, Profession, ProfessionSpecialization, Race, Specialization

CLASSES = [
    # slug, nom, couleur
    ("warrior", "Guerrier", "#C69B6D"),
    ("paladin", "Paladin", "#F48CBA"),
    ("hunter", "Chasseur", "#AAD372"),
    ("rogue", "Voleur", "#FFF468"),
    ("priest", "Prêtre", "#FFFFFF"),
    ("shaman", "Chaman", "#0070DD"),
    ("mage", "Mage", "#3FC7EB"),
    ("warlock", "Démoniste", "#8788EE"),
    ("druid", "Druide", "#FF7C0A"),
]

SPECIALIZATIONS = {
    "warrior": [
        ("arms", "Armes", ["dps"]),
        ("fury", "Fureur", ["dps"]),
        ("protection", "Protection", ["tank"]),
    ],
    "paladin": [
        ("holy", "Sacré", ["heal"]),
        ("protection", "Protection", ["tank"]),
        ("retribution", "Vindicte", ["dps"]),
    ],
    "hunter": [
        ("beast-mastery", "Maîtrise des bêtes", ["dps"]),
        ("marksmanship", "Précision", ["dps"]),
        ("survival", "Survie", ["dps"]),
    ],
    "rogue": [
        ("assassination", "Assassinat", ["dps"]),
        ("combat", "Combat", ["dps"]),
        ("subtlety", "Finesse", ["dps"]),
    ],
    "priest": [
        ("discipline", "Discipline", ["heal"]),
        ("holy", "Sacré", ["heal"]),
        ("shadow", "Ombre", ["dps"]),
    ],
    "shaman": [
        ("elemental", "Élémentaire", ["dps"]),
        ("enhancement", "Amélioration", ["dps"]),
        ("restoration", "Restauration", ["heal"]),
    ],
    "mage": [("arcane", "Arcanes", ["dps"]), ("fire", "Feu", ["dps"]), ("frost", "Givre", ["dps"])],
    "warlock": [
        ("affliction", "Affliction", ["dps"]),
        ("demonology", "Démonologie", ["dps"]),
        ("destruction", "Destruction", ["dps"]),
    ],
    "druid": [
        ("balance", "Équilibre", ["dps"]),
        ("feral", "Farouche", ["tank", "dps"]),
        ("restoration", "Restauration", ["heal"]),
    ],
}

RACES = [
    # slug, nom, faction, classes — d'après la table CharBaseInfo du client WoW Forever (build 1.60.1)
    ("human", "Humain", "alliance", ["warrior", "paladin", "hunter", "rogue", "priest", "mage", "warlock"]),
    ("dwarf", "Nain", "alliance", ["warrior", "paladin", "hunter", "rogue", "priest", "shaman"]),
    ("night-elf", "Elfe de la nuit", "alliance", ["warrior", "hunter", "rogue", "priest", "druid"]),
    ("gnome", "Gnome", "alliance", ["warrior", "rogue", "priest", "mage", "warlock"]),
    (
        "skyborn-alliance",
        "Éolide de l'Ordre suprême",
        "alliance",
        ["warrior", "hunter", "rogue", "mage", "druid"],
    ),
    ("orc", "Orc", "horde", ["warrior", "hunter", "rogue", "shaman", "mage", "warlock"]),
    ("undead", "Mort-vivant", "horde", ["warrior", "paladin", "rogue", "priest", "mage", "warlock"]),
    ("tauren", "Tauren", "horde", ["warrior", "hunter", "shaman", "druid"]),
    ("troll", "Troll", "horde", ["warrior", "hunter", "rogue", "priest", "shaman", "mage", "warlock"]),
    ("skyborn-horde", "Éolide sculpte-vents", "horde", ["warrior", "hunter", "rogue", "shaman", "druid"]),
]

PROFESSIONS = [
    # slug, nom, type
    ("alchemy", "Alchimie", "primary"),
    ("blacksmithing", "Forge", "primary"),
    ("enchanting", "Enchantement", "primary"),
    ("engineering", "Ingénierie", "primary"),
    ("herbalism", "Herboristerie", "primary"),
    ("leatherworking", "Travail du cuir", "primary"),
    ("mining", "Minage", "primary"),
    ("skinning", "Dépeçage", "primary"),
    ("tailoring", "Couture", "primary"),
    ("cooking", "Cuisine", "secondary"),
    ("first-aid", "Secourisme", "secondary"),
    ("fishing", "Pêche", "secondary"),
]

PROFESSION_SPECIALIZATIONS = {
    "blacksmithing": [
        ("armorsmith", "Armurier"),
        ("weaponsmith", "Fabricant d'armes"),
        ("swordsmith", "Forgeron d'épées"),
        ("axesmith", "Forgeron de haches"),
        ("hammersmith", "Forgeron de masses"),
    ],
    "engineering": [("gnomish", "Ingénierie gnome"), ("goblin", "Ingénierie gobeline")],
    "leatherworking": [
        ("elemental", "Travail du cuir élémentaire"),
        ("tribal", "Travail du cuir tribal"),
        ("dragonscale", "Travail du cuir en écailles de dragon"),
    ],
}


INSTANCES = [
    # slug, nom, type, taille, niveau min, niveau recommandé
    ("ragefire-chasm", "Gouffre de Ragefeu", "dungeon", 5, 10, 15),
    ("deadmines", "Les Mortemines", "dungeon", 5, 15, 20),
    ("wailing-caverns", "Cavernes des Lamentations", "dungeon", 5, 15, 20),
    ("shadowfang-keep", "Donjon d'Ombrecroc", "dungeon", 5, 20, 26),
    ("blackfathom-deeps", "Profondeurs de Brassenoire", "dungeon", 5, 20, 28),
    ("stockade", "La Prison", "dungeon", 5, 20, 28),
    ("gnomeregan", "Gnomeregan", "dungeon", 5, 25, 33),
    ("razorfen-kraul", "Kraal de Tranchebauge", "dungeon", 5, 25, 34),
    ("scarlet-monastery", "Monastère Écarlate", "dungeon", 5, 30, 40),
    ("razorfen-downs", "Souilles de Tranchebauge", "dungeon", 5, 35, 42),
    ("uldaman", "Uldaman", "dungeon", 5, 35, 46),
    ("zul-farrak", "Zul'Farrak", "dungeon", 5, 40, 48),
    ("maraudon", "Maraudon", "dungeon", 5, 40, 50),
    ("sunken-temple", "Temple d'Atal'Hakkar", "dungeon", 5, 45, 53),
    ("blackrock-depths", "Profondeurs de Blackrock", "dungeon", 5, 48, 56),
    ("lower-blackrock-spire", "Pic Blackrock inférieur", "dungeon", 5, 50, 58),
    ("dire-maul", "Hache-Tripes", "dungeon", 5, 54, 60),
    ("scholomance", "Scholomance", "dungeon", 5, 55, 60),
    ("stratholme", "Stratholme", "dungeon", 5, 55, 60),
    ("upper-blackrock-spire", "Pic Blackrock supérieur", "raid", 10, 55, 60),
    ("zul-gurub", "Zul'Gurub", "raid", 20, 58, 60),
    ("ruins-of-ahn-qiraj", "Ruines d'Ahn'Qiraj", "raid", 20, 58, 60),
    ("onyxia", "Repaire d'Onyxia", "raid", 40, 58, 60),
    ("molten-core", "Cœur du Magma", "raid", 40, 58, 60),
    ("blackwing-lair", "Repaire de l'Aile noire", "raid", 40, 60, 60),
    ("temple-of-ahn-qiraj", "Temple d'Ahn'Qiraj", "raid", 40, 60, 60),
    ("naxxramas", "Naxxramas", "raid", 40, 60, 60),
    ("warsong-gulch", "Goulet des Chanteguerres", "battleground", 10, 10, 60),
    ("arathi-basin", "Bassin Arathi", "battleground", 15, 20, 60),
    ("alterac-valley", "Vallée d'Alterac", "battleground", 40, 51, 60),
]

# Besoins par rôle proposés par défaut selon le type et la taille.
DEFAULT_NEEDS = {
    ("dungeon", 5): (1, 1, 3),
    ("raid", 10): (2, 3, 5),
    ("raid", 20): (2, 5, 13),
    ("raid", 40): (4, 10, 26),
}


def seed() -> None:
    # L'ancienne race unique « skyborn » devient la variante Alliance : les persos existants la gardent.
    Race.objects.filter(slug="skyborn").update(slug="skyborn-alliance")
    classes: dict[str, PlayerClass] = {}
    for order, (slug, name, color) in enumerate(CLASSES):
        classes[slug], _ = PlayerClass.objects.update_or_create(
            slug=slug, defaults={"name": name, "color": color, "order": order}
        )

    for class_slug, specs in SPECIALIZATIONS.items():
        for order, (slug, name, roles) in enumerate(specs):
            Specialization.objects.update_or_create(
                slug=f"{class_slug}-{slug}",
                defaults={"player_class": classes[class_slug], "name": name, "roles": roles, "order": order},
            )

    for order, (slug, name, faction, class_slugs) in enumerate(RACES):
        race, _ = Race.objects.update_or_create(
            slug=slug, defaults={"name": name, "faction": faction, "order": order}
        )
        race.classes.set([classes[s] for s in class_slugs])

    for order, (slug, name, kind, size, min_level, recommended) in enumerate(INSTANCES):
        tanks, heals, dps = DEFAULT_NEEDS.get((kind, size), (None, None, None))
        Instance.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "kind": kind,
                "size": size,
                "min_level": min_level,
                "recommended_level": recommended,
                "default_tanks": tanks,
                "default_heals": heals,
                "default_dps": dps,
                "order": order,
            },
        )

    for order, (slug, name, kind) in enumerate(PROFESSIONS):
        profession, _ = Profession.objects.update_or_create(
            slug=slug, defaults={"name": name, "kind": kind, "order": order}
        )
        for spec_slug, spec_name in PROFESSION_SPECIALIZATIONS.get(slug, []):
            ProfessionSpecialization.objects.update_or_create(
                slug=f"{slug}-{spec_slug}", defaults={"profession": profession, "name": spec_name}
            )
