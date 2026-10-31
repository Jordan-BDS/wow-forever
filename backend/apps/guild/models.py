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
        max_length=1000,
        help_text=(
            "Affichées en citation sur l'accueil. "
            "Retours à la ligne conservés, une ligne vide sépare les strophes."
        ),
    )
    discord_channel_id = models.CharField(
        "Salon Discord général",
        max_length=32,
        blank=True,
        help_text="Secours : reçoit les annonces dont le salon dédié n'est pas renseigné.",
    )
    discord_agenda_channel_id = models.CharField(
        "Salon Discord de l'agenda",
        max_length=32,
        blank=True,
        help_text="Messages d'inscription des événements, déplacements, annulations, rappels, compositions.",
    )
    discord_crafts_channel_id = models.CharField(
        "Salon Discord des demandes de craft",
        max_length=32,
        blank=True,
        help_text="Nouvelles demandes de craft.",
    )
    discord_polls_channel_id = models.CharField(
        "Salon Discord des sondages", max_length=32, blank=True, help_text="Ouverture, rappels et résultats."
    )
    reminder_minutes = models.PositiveSmallIntegerField(
        "Rappel avant un événement (minutes)", default=60, help_text="0 = pas de rappel."
    )
    accepted_interface_versions = models.CharField(
        "Versions d'interface acceptées",
        max_length=64,
        blank=True,
        default="16001",
        help_text=(
            "Numéros d'interface du client de jeu acceptés à l'import (WoW Forever : 16001), "
            "séparés par des virgules. Vide : tout accepter."
        ),
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

    @property
    def accepted_interface_set(self) -> set[int]:
        """Numéros d'interface acceptés à l'import ; vide = tout accepter (non numériques ignorés)."""
        return {
            int(part)
            for part in self.accepted_interface_versions.replace(";", ",").split(",")
            if part.strip().isdigit()
        }
