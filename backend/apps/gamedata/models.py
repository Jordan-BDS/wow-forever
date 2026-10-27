"""Données de référence du jeu : classes, races, spécialisations, métiers. Administrables, pré-remplies."""

from django.db import models

from apps.guild.models import Faction


class Role(models.TextChoices):
    TANK = "tank", "Tank"
    HEAL = "heal", "Heal"
    DPS = "dps", "DPS"


ROLE_ORDER = {Role.TANK: 0, Role.HEAL: 1, Role.DPS: 2}


class PlayerClass(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField("Nom", max_length=32)
    color = models.CharField("Couleur officielle", max_length=7, help_text="Hexadécimal, ex. #C69B6D")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "classe"
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def roles(self) -> list[str]:
        found = {role for spec in self.specializations.all() for role in spec.roles}
        return sorted(found, key=lambda r: ROLE_ORDER[Role(r)])


class Race(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField("Nom", max_length=32)
    faction = models.CharField(
        "Faction", max_length=16, choices=Faction.choices, blank=True, help_text="Vide = les deux factions"
    )
    classes = models.ManyToManyField(PlayerClass, related_name="races", verbose_name="Classes jouables")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "race"
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    def available_for(self, faction: str) -> bool:
        return not self.faction or not faction or self.faction == faction


class Specialization(models.Model):
    player_class = models.ForeignKey(PlayerClass, on_delete=models.CASCADE, related_name="specializations")
    slug = models.SlugField(unique=True, help_text="Préfixé par la classe, ex. druid-restoration")
    name = models.CharField("Nom", max_length=32)
    roles = models.JSONField("Rôles possibles", default=list, help_text='Liste parmi "tank", "heal", "dps"')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "spécialisation"
        ordering = ["player_class__order", "order"]

    def __str__(self) -> str:
        return f"{self.player_class.name} {self.name}"


class InstanceKind(models.TextChoices):
    DUNGEON = "dungeon", "Donjon"
    RAID = "raid", "Raid"
    BATTLEGROUND = "battleground", "Champ de bataille"


class Instance(models.Model):
    """Donjon, raid ou champ de bataille, pour cibler un événement."""

    slug = models.SlugField(unique=True)
    name = models.CharField("Nom", max_length=64)
    kind = models.CharField("Type", max_length=16, choices=InstanceKind.choices)
    size = models.PositiveSmallIntegerField("Taille du groupe")
    min_level = models.PositiveSmallIntegerField("Niveau minimum", default=1)
    recommended_level = models.PositiveSmallIntegerField("Niveau recommandé", default=60)
    default_tanks = models.PositiveSmallIntegerField("Tanks par défaut", null=True, blank=True)
    default_heals = models.PositiveSmallIntegerField("Heals par défaut", null=True, blank=True)
    default_dps = models.PositiveSmallIntegerField("DPS par défaut", null=True, blank=True)
    is_forever = models.BooleanField("Spécifique WoW Forever", default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "instance"
        ordering = ["kind", "order", "recommended_level", "name"]

    def __str__(self) -> str:
        return self.name


class ProfessionKind(models.TextChoices):
    PRIMARY = "primary", "Principal"
    SECONDARY = "secondary", "Secondaire"


class Profession(models.Model):
    MAX_SKILL = 300
    MAX_PRIMARY = 2

    slug = models.SlugField(unique=True)
    name = models.CharField("Nom", max_length=32)
    kind = models.CharField("Type", max_length=16, choices=ProfessionKind.choices)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "métier"
        ordering = ["kind", "order", "name"]

    def __str__(self) -> str:
        return self.name


class ProfessionSpecialization(models.Model):
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name="specializations")
    slug = models.SlugField(unique=True, help_text="Préfixé par le métier, ex. engineering-gnomish")
    name = models.CharField("Nom", max_length=48)

    class Meta:
        verbose_name = "spécialisation de métier"
        ordering = ["profession__order", "name"]

    def __str__(self) -> str:
        return f"{self.profession.name} : {self.name}"


# --- Index du jeu (importé depuis les données client, cf. cahier des charges § 5) ---


class ImportRun(models.Model):
    """Trace du dernier import de données client."""

    build = models.CharField("Build du client", max_length=32)
    product = models.CharField("Produit", max_length=32, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    counts = models.JSONField(default=dict)

    class Meta:
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        return f"{self.product} {self.build} ({self.imported_at:%d/%m/%Y})"


class ItemSet(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=120)
    bonuses = models.JSONField(default=list, help_text="[{threshold, spell_id, description}]")

    class Meta:
        verbose_name = "set d'objets"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Item(models.Model):
    """Index minimal d'un objet. Le détail (infobulle) vient de Wowhead via l'ID."""

    id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    quality = models.PositiveSmallIntegerField(default=1)
    item_level = models.PositiveSmallIntegerField(default=1)
    required_level = models.PositiveSmallIntegerField(default=0)
    inventory_type = models.PositiveSmallIntegerField(default=0, db_index=True)
    class_id = models.PositiveSmallIntegerField(default=0)
    subclass_id = models.PositiveSmallIntegerField(default=0)
    allowable_class = models.IntegerField(default=-1, help_text="Masque de classes, -1 = toutes")
    is_unique = models.BooleanField(default=False)
    item_set = models.ForeignKey(
        ItemSet, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    icon = models.CharField(max_length=80, blank=True)
    stats = models.JSONField(default=dict, help_text="{type de stat: valeur}")
    description = models.CharField(max_length=255, blank=True)
    is_forever = models.BooleanField(
        "Géré à la main", default=False, help_text="Ajout ou correction manuelle, jamais écrasé par l'import."
    )

    class Meta:
        verbose_name = "objet"
        ordering = ["name"]
        indexes = [models.Index(fields=["name"]), models.Index(fields=["name_en"])]

    def __str__(self) -> str:
        return self.name


class Enchantment(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=120)
    spell_id = models.PositiveIntegerField(default=0)
    icon = models.CharField(max_length=80, blank=True)
    stats = models.JSONField(default=dict)
    slot_mask = models.IntegerField(default=0, help_text="Masque d'InventoryType autorisés (0 = inconnu)")
    equipped_class = models.SmallIntegerField(
        default=-1, help_text="Classe d'objet requise (2 arme, 4 armure), -1 = toutes"
    )
    equipped_subclass_mask = models.IntegerField(
        default=0, help_text="Masque de sous-classes autorisées (0 = toutes)"
    )
    required_skill = models.PositiveIntegerField(default=0)
    required_skill_rank = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "enchantement"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TalentTree(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    player_class = models.ForeignKey(PlayerClass, on_delete=models.CASCADE, related_name="talent_trees")
    name = models.CharField(max_length=64)
    background = models.CharField(max_length=64, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "arbre de talents"
        ordering = ["player_class__order", "order"]

    def __str__(self) -> str:
        return f"{self.player_class.name} — {self.name}"


class Talent(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    tree = models.ForeignKey(TalentTree, on_delete=models.CASCADE, related_name="talents")
    name = models.CharField(max_length=80)
    icon = models.CharField(max_length=80, blank=True)
    row = models.PositiveSmallIntegerField()
    column = models.PositiveSmallIntegerField()
    rank_spells = models.JSONField(default=list, help_text="ID de sort par rang")
    prerequisite = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    prerequisite_rank = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "talent"
        ordering = ["tree", "row", "column"]

    def __str__(self) -> str:
        return self.name

    @property
    def max_rank(self) -> int:
        return len(self.rank_spells)


class Recipe(models.Model):
    id = models.PositiveIntegerField(primary_key=True, help_text="ID du sort de fabrication")
    profession = models.ForeignKey(Profession, on_delete=models.CASCADE, related_name="recipes")
    name = models.CharField(max_length=120)
    icon = models.CharField(max_length=80, blank=True)
    min_skill = models.PositiveSmallIntegerField(
        default=1, help_text="Estimé depuis les paliers jaune/gris du client, corrigeable à la main."
    )
    skill_yellow = models.PositiveSmallIntegerField(default=0)
    skill_grey = models.PositiveSmallIntegerField(default=0)
    product = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True, related_name="recipes"
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    reagents = models.JSONField(default=list, help_text="[{item_id, name, count}]")
    acquire_method = models.PositiveSmallIntegerField(default=0)
    is_forever = models.BooleanField(
        "Géré à la main", default=False, help_text="Ajout ou correction manuelle, jamais écrasé par l'import."
    )

    class Meta:
        verbose_name = "recette"
        ordering = ["profession", "min_skill", "name"]

    def __str__(self) -> str:
        return self.name
