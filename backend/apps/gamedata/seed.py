"""
Données vanilla (Classic Era) pré-remplies, plus la race Skyborn de WoW Forever.
`seed()` est idempotent : rejouable sans dupliquer, met à jour noms et couleurs,
ne supprime jamais rien (les ajouts faits via l'admin survivent).
"""

from .models import PlayerClass, Profession, ProfessionSpecialization, Race, Specialization

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
    # slug, nom, faction ("" = les deux), classes
    ("human", "Humain", "alliance", ["warrior", "paladin", "rogue", "priest", "mage", "warlock"]),
    ("dwarf", "Nain", "alliance", ["warrior", "paladin", "hunter", "rogue", "priest"]),
    ("night-elf", "Elfe de la nuit", "alliance", ["warrior", "hunter", "rogue", "priest", "druid"]),
    ("gnome", "Gnome", "alliance", ["warrior", "rogue", "mage", "warlock"]),
    ("orc", "Orc", "horde", ["warrior", "hunter", "rogue", "shaman", "warlock"]),
    ("undead", "Mort-vivant", "horde", ["warrior", "rogue", "priest", "mage", "warlock"]),
    ("tauren", "Tauren", "horde", ["warrior", "hunter", "shaman", "druid"]),
    ("troll", "Troll", "horde", ["warrior", "hunter", "rogue", "priest", "shaman", "mage"]),
    # WoW Forever : faction et classes à confirmer à la sortie (cf. cahier des charges, section 3).
    ("skyborn", "Skyborn", "", ["warrior", "hunter", "rogue", "druid", "shaman", "mage"]),
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


def seed() -> None:
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

    for order, (slug, name, kind) in enumerate(PROFESSIONS):
        profession, _ = Profession.objects.update_or_create(
            slug=slug, defaults={"name": name, "kind": kind, "order": order}
        )
        for spec_slug, spec_name in PROFESSION_SPECIALIZATIONS.get(slug, []):
            ProfessionSpecialization.objects.update_or_create(
                slug=f"{slug}-{spec_slug}", defaults={"profession": profession, "name": spec_name}
            )
