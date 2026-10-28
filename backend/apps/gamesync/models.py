"""
Synchronisation depuis le jeu : appairage du compagnon, archive brute des imports, instantanés par personnage.
Les règles sont décrites au cahier des charges, étape 11.
"""

from django.conf import settings
from django.db import models


class PairingCode(models.Model):
    """Code à 6 caractères affiché sur le site, saisi dans le compagnon, échangé contre un jeton."""

    LIFETIME_MINUTES = 10
    ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O ni 1/I
    LENGTH = 6

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pairing_codes")
    code = models.CharField(max_length=8, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "code d'appairage"

    def __str__(self) -> str:
        return f"{self.code} ({self.user})"


class CompanionDevice(models.Model):
    """Une installation du compagnon sur une machine ; le jeton n'est stocké que haché."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="companions")
    name = models.CharField("Machine", max_length=64)
    token_hash = models.CharField(max_length=64, unique=True)
    token_prefix = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "compagnon"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.user})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class ImportSource(models.TextChoices):
    PASTE = "paste", "Collage sur le site"
    COMPANION = "companion", "Compagnon"


class ImportBatch(models.Model):
    """Un code d'export accepté, conservé tel quel : les imports sont rejouables."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="import_batches"
    )
    device = models.ForeignKey(CompanionDevice, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(max_length=16, choices=ImportSource.choices)
    fingerprint = models.CharField(max_length=64, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)
    format_version = models.PositiveSmallIntegerField()
    addon_version = models.CharField(max_length=32, blank=True)
    install_id = models.CharField(max_length=64, blank=True)
    code = models.TextField(help_text="Le code d'export tel que reçu.")
    summary = models.JSONField(default=dict)

    class Meta:
        verbose_name = "import"
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"Import {self.pk} de {self.user} ({self.source})"


class SnapshotStatus(models.TextChoices):
    APPLIED = "applied", "Mis à jour"
    CREATED = "created", "Créé"
    PENDING = "pending", "À rattacher"
    IGNORED = "ignored", "Ignoré"
    STALE = "stale", "Plus ancien que le dernier import"
    REFUSED = "refused", "Refusé"


class CharacterSnapshot(models.Model):
    """L'état d'un personnage dans un code d'export, et ce que le site en a fait."""

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="snapshots")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    character = models.ForeignKey(
        "characters.Character", on_delete=models.SET_NULL, null=True, blank=True, related_name="snapshots"
    )
    candidate = models.ForeignKey(
        "characters.Character",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Personnage du site proposé pour la fusion (statut « à rattacher »).",
    )
    guid = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=24)
    surname = models.CharField(max_length=24, blank=True)
    realm = models.CharField(max_length=64, blank=True)
    exported_at = models.DateTimeField()
    day = models.DateField(help_text="Jour de l'export en Europe/Paris (un instantané conservé par jour).")
    data = models.JSONField()
    status = models.CharField(max_length=10, choices=SnapshotStatus.choices)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "instantané de personnage"
        ordering = ["-exported_at"]
        indexes = [models.Index(fields=["character", "day"])]

    def __str__(self) -> str:
        return f"{self.full_name} — {self.get_status_display()}"

    @property
    def full_name(self) -> str:
        return f"{self.name} {self.surname}".strip()


class IgnoredCharacter(models.Model):
    """Personnage du jeu que le joueur ne veut pas voir sur le site (alt banque…)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ignored_characters"
    )
    guid = models.CharField(max_length=64)
    name = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "personnage ignoré"
        constraints = [models.UniqueConstraint(fields=["user", "guid"], name="unique_ignored_guid_per_user")]

    def __str__(self) -> str:
        return f"{self.name or self.guid} ({self.user})"


class WeeklyTitle(models.Model):
    """Titre de la semaine, attribué le lundi à 10h sur la semaine close, jamais remis en cause."""

    week_start = models.DateField(help_text="Lundi de la semaine récompensée.")
    key = models.CharField(max_length=32)
    label = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_titles")
    character = models.ForeignKey(
        "characters.Character", on_delete=models.SET_NULL, null=True, blank=True, related_name="weekly_titles"
    )
    value = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "titre de la semaine"
        ordering = ["-week_start", "key"]
        constraints = [models.UniqueConstraint(fields=["week_start", "key"], name="unique_title_per_week")]

    def __str__(self) -> str:
        return f"{self.label} — semaine du {self.week_start} : {self.user}"
