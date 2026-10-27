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
