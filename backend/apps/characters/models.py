from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.gamedata.models import (
    PlayerClass,
    Profession,
    ProfessionSpecialization,
    Race,
    Role,
    Specialization,
)


class CharacterSource(models.TextChoices):
    MANUAL = "manual", "Saisie manuelle"
    BLIZZARD = "blizzard", "API Blizzard"


class Character(models.Model):
    MAX_LEVEL = 60

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="characters")
    name = models.CharField("Nom", max_length=24)
    player_class = models.ForeignKey(PlayerClass, on_delete=models.PROTECT, verbose_name="Classe")
    race = models.ForeignKey(Race, on_delete=models.PROTECT, verbose_name="Race")
    level = models.PositiveSmallIntegerField("Niveau", default=1)
    main_role = models.CharField("Rôle principal", max_length=8, choices=Role.choices)
    off_role = models.CharField("Rôle secondaire", max_length=8, choices=Role.choices, blank=True)
    specialization = models.ForeignKey(
        Specialization, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Spécialisation"
    )
    is_main = models.BooleanField("Main", default=False)
    note = models.TextField("Note", blank=True)
    source = models.CharField(max_length=16, choices=CharacterSource.choices, default=CharacterSource.MANUAL)
    external_id = models.CharField("Identifiant externe", max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "personnage"
        ordering = ["-is_main", "-level", "name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="unique_character_name_ci"),
            models.UniqueConstraint(
                fields=["owner"], condition=models.Q(is_main=True), name="one_main_per_owner"
            ),
            models.CheckConstraint(condition=models.Q(level__gte=1, level__lte=60), name="level_range"),
        ]

    def __str__(self) -> str:
        return self.name


class CharacterProfession(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="professions")
    profession = models.ForeignKey(Profession, on_delete=models.PROTECT, verbose_name="Métier")
    skill = models.PositiveSmallIntegerField("Compétence", default=1)
    specialization = models.ForeignKey(
        ProfessionSpecialization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Spécialisation",
    )

    class Meta:
        verbose_name = "métier de personnage"
        ordering = ["profession__kind", "profession__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["character", "profession"], name="unique_profession_per_character"
            ),
            models.CheckConstraint(condition=models.Q(skill__lte=300), name="skill_max"),
        ]

    def __str__(self) -> str:
        return f"{self.character} — {self.profession} {self.skill}"


# --- Fiche de personnage : sets d'équipement et builds de talents (lot 5) ---


class EquipmentSet(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="equipment_sets")
    name = models.CharField("Nom", max_length=40)
    is_primary = models.BooleanField("Set principal", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "set d'équipement"
        ordering = ["-is_primary", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character"],
                condition=models.Q(is_primary=True),
                name="one_primary_set_per_character",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character} — {self.name}"


class EquipmentSlot(models.Model):
    """Un emplacement d'un set : objet + enchantement optionnel."""

    equipment_set = models.ForeignKey(EquipmentSet, on_delete=models.CASCADE, related_name="slots")
    slot = models.CharField(max_length=16)
    item = models.ForeignKey("gamedata.Item", on_delete=models.SET_NULL, null=True, blank=True)
    enchantment = models.ForeignKey("gamedata.Enchantment", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "emplacement"
        constraints = [models.UniqueConstraint(fields=["equipment_set", "slot"], name="unique_slot_per_set")]

    def __str__(self) -> str:
        return f"{self.slot}: {self.item or '—'}"


class TalentBuild(models.Model):
    """Build de talents : l'ordre d'attribution des points est conservé (acquis puis projetés)."""

    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="talent_builds")
    name = models.CharField("Nom", max_length=40)
    is_active = models.BooleanField("Build actif", default=False)
    points = models.JSONField("Points dans l'ordre", default=list, help_text="Liste d'ID de talents")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "build de talents"
        ordering = ["-is_active", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character"],
                condition=models.Q(is_active=True),
                name="one_active_build_per_character",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character} — {self.name}"
