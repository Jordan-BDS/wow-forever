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
    values = models.TextField(
        "Valeurs de la guilde",
        blank=True,
        max_length=600,
        help_text="Affichées en citation sur l'accueil. Une ligne vide sépare les paragraphes.",
    )
    discord_channel_id = models.CharField(
        "Salon Discord des annonces", max_length=32, blank=True, help_text="Le bot y publie les annonces."
    )
    reminder_minutes = models.PositiveSmallIntegerField(
        "Rappel avant un événement (minutes)", default=60, help_text="0 = pas de rappel."
    )
    # Connexion Discord, saisie par le GM sur le site (les variables d'environnement servent de secours).
    discord_client_id = models.CharField("Client ID de l'application Discord", max_length=32, blank=True)
    discord_client_secret = models.CharField("Client secret", max_length=128, blank=True)
    discord_bot_token = models.CharField("Token du bot", max_length=128, blank=True)
    discord_guild_id = models.CharField("ID du serveur Discord", max_length=32, blank=True)
    discord_allowed_role_ids = models.CharField(
        "IDs des rôles autorisés", max_length=255, blank=True, help_text="Séparés par des virgules."
    )
    discord_first_gm_id = models.CharField("ID Discord du premier GM", max_length=32, blank=True)
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
