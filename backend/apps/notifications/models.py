"""
Outbox de notifications : le site écrit, le bot Discord dépile et envoie.
Si le bot est arrêté, rien n'est perdu : les lignes attendent en `pending`.
"""

from django.conf import settings
from django.db import models


class NotificationKind(models.TextChoices):
    EVENT_CREATED = "event_created", "Événement créé"
    EVENT_CANCELLED = "event_cancelled", "Événement annulé"
    EVENT_RESCHEDULED = "event_rescheduled", "Événement déplacé"
    EVENT_REMINDER = "event_reminder", "Rappel d'événement"
    EVENT_SYNC = "event_sync", "Synchronisation Discord d'un événement"
    COMPOSITION = "composition", "Composition publiée"
    PLACEMENT = "placement", "Placement (confirmé / banc)"
    POLL_OPENED = "poll_opened", "Sondage ouvert"
    POLL_REMINDER = "poll_reminder", "Rappel de sondage"
    POLL_VALIDATED = "poll_validated", "Sondage validé"
    POLL_CANCELLED = "poll_cancelled", "Sondage annulé"
    POLL_SYNC = "poll_sync", "Synchronisation Discord d'un sondage"
    DISCORD_CLEANUP = "discord_cleanup", "Nettoyage Discord après une suppression"
    CRAFT_REQUEST = "craft_request", "Demande de craft"
    CRAFT_UPDATE = "craft_update", "Suivi de demande de craft"


# Catégories de MP que chaque joueur peut couper depuis son profil.
DM_PREFERENCE_KINDS = {
    "placement": "Placement dans un événement",
    "reminder": "Rappels personnels avant un événement",
    "craft": "Demandes de craft",
}

DM_PREFERENCE_FOR_KIND = {
    NotificationKind.PLACEMENT: "placement",
    NotificationKind.EVENT_REMINDER: "reminder",
    NotificationKind.CRAFT_REQUEST: "craft",
    NotificationKind.CRAFT_UPDATE: "craft",
}


# Salon de destination (champ de GuildSettings) de chaque type de message de salon ; `discord_channel_id`
# (le salon général) sert de secours quand le salon dédié n'est pas renseigné.
CHANNEL_FIELD_FOR_KIND = {
    NotificationKind.EVENT_CREATED: "discord_agenda_channel_id",
    NotificationKind.EVENT_CANCELLED: "discord_agenda_channel_id",
    NotificationKind.EVENT_RESCHEDULED: "discord_agenda_channel_id",
    NotificationKind.EVENT_REMINDER: "discord_agenda_channel_id",
    NotificationKind.EVENT_SYNC: "discord_agenda_channel_id",
    NotificationKind.COMPOSITION: "discord_agenda_channel_id",
    NotificationKind.POLL_OPENED: "discord_polls_channel_id",
    NotificationKind.POLL_REMINDER: "discord_polls_channel_id",
    NotificationKind.POLL_VALIDATED: "discord_polls_channel_id",
    NotificationKind.POLL_CANCELLED: "discord_polls_channel_id",
    NotificationKind.POLL_SYNC: "discord_polls_channel_id",
    NotificationKind.CRAFT_REQUEST: "discord_crafts_channel_id",
}


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    SENT = "sent", "Envoyée"
    FAILED = "failed", "Échec"
    SKIPPED = "skipped", "Ignorée"


class Notification(models.Model):
    kind = models.CharField(max_length=32, choices=NotificationKind.choices)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Vide = message dans le salon de la guilde.",
    )
    text = models.TextField()
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sync_notifications",
        help_text="Événement à synchroniser avec Discord (kind = event_sync).",
    )
    poll = models.ForeignKey(
        "polls.Poll",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sync_notifications",
        help_text="Sondage à synchroniser avec Discord (kind = poll_sync).",
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Identifiants Discord à effacer (kind = discord_cleanup) : l'objet du site n'existe plus.",
    )
    status = models.CharField(
        max_length=10, choices=NotificationStatus.choices, default=NotificationStatus.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "notification"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        target = self.recipient or "salon"
        return f"[{self.status}] {self.kind} → {target}"

    @property
    def is_dm(self) -> bool:
        return self.recipient_id is not None
