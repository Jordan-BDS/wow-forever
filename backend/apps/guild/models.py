from django.db import models


class Faction(models.TextChoices):
    ALLIANCE = "alliance", "Alliance"
    HORDE = "horde", "Horde"


class GuildSettings(models.Model):
    """Paramètres globaux de la guilde (une seule ligne, pk=1)."""

    SINGLETON_PK = 1

    name = models.CharField("Nom de la guilde", max_length=24, blank=True)
    faction = models.CharField("Faction", max_length=16, choices=Faction.choices, blank=True)
    realm = models.CharField("Royaume", max_length=64, blank=True)
    discord_channel_id = models.CharField(
        "Salon Discord des annonces", max_length=32, blank=True, help_text="Le bot y publie les annonces."
    )
    reminder_minutes = models.PositiveSmallIntegerField(
        "Rappel avant un événement (minutes)", default=60, help_text="0 = pas de rappel."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "paramètres de guilde"
        verbose_name_plural = "paramètres de guilde"

    def __str__(self) -> str:
        return self.name or "Guilde (sans nom)"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "GuildSettings":
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
