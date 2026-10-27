"""
Logique synchrone du bot (ORM, règles métier). Le bot l'appelle via `sync_to_async`,
ce qui permet de la tester sans Discord.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import DeactivationReason, User
from apps.accounts.services import deactivate_user
from apps.characters.models import Character
from apps.events import services as event_services
from apps.events.models import Event, EventStatus
from apps.gamedata.models import Role
from apps.guild.models import GuildSettings
from apps.notifications.models import Notification, NotificationStatus
from apps.notifications.services import discord_time, event_url

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


# --- outbox ------------------------------------------------------------------------


def pending_notifications(limit: int = 20) -> list[Notification]:
    return list(
        Notification.objects.filter(status=NotificationStatus.PENDING, attempts__lt=MAX_ATTEMPTS)
        .select_related("recipient")
        .order_by("created_at")[:limit]
    )


def mark_sent(notification: Notification) -> None:
    notification.status = NotificationStatus.SENT
    notification.sent_at = timezone.now()
    notification.attempts += 1
    notification.save(update_fields=["status", "sent_at", "attempts"])


def mark_failed(notification: Notification, error: str) -> None:
    notification.attempts += 1
    notification.error = error[:500]
    if notification.attempts >= MAX_ATTEMPTS:
        notification.status = NotificationStatus.FAILED
    notification.save(update_fields=["status", "error", "attempts"])
    logger.warning(
        "Notification %s en échec (%s/%s) : %s", notification.pk, notification.attempts, MAX_ATTEMPTS, error
    )


def mark_skipped(notification: Notification, reason: str) -> None:
    notification.status = NotificationStatus.SKIPPED
    notification.error = reason
    notification.save(update_fields=["status", "error"])


def announcement_channel_id() -> int | None:
    raw = GuildSettings.load().discord_channel_id
    return int(raw) if raw.isdigit() else None


# --- accès -----------------------------------------------------------------------------


def has_allowed_role(role_ids: list[str]) -> bool:
    return bool(set(settings.DISCORD_ALLOWED_ROLE_IDS) & set(role_ids))


def revoke_access(discord_id: str, reason: str) -> bool:
    """Désactive le compte lié à cet ID Discord. Renvoie True si un compte actif a été coupé."""
    user = User.objects.filter(discord_id=discord_id, is_active=True).first()
    if not user:
        return False
    deactivate_user(user, DeactivationReason.DISCORD)
    logger.info("Accès révoqué pour %s : %s", user, reason)
    return True


# --- commandes slash -------------------------------------------------------------------


def upcoming_events(limit: int = 5) -> list[Event]:
    now = timezone.now()
    return [
        e
        for e in Event.objects.filter(status=EventStatus.PLANNED, starts_at__gte=now - timedelta(hours=3))
        .select_related("organizer")
        .prefetch_related("signups")
        .order_by("starts_at")[: limit * 2]
        if e.effective_status == EventStatus.PLANNED
    ][:limit]


def upcoming_events_text() -> str:
    events = upcoming_events()
    if not events:
        return (
            "Rien de prévu pour l'instant. "
            + f"{settings.SITE_URL}/agenda/nouveau pour proposer une sortie !"
        )
    lines = ["**Prochains événements**"]
    for event in events:
        count = sum(1 for s in event.signups.all() if s.status != "absent")
        size = f"/{event.max_size}" if event.max_size else ""
        lines.append(
            f"• {discord_time(event.starts_at, 'f')} — **{event.title}** ({count}{size} inscrits)"
            f" {event_url(event)}"
        )
    return "\n".join(lines)


def event_choices(current: str) -> list[tuple[str, int]]:
    """(libellé, id) des événements à venir filtrés par le texte tapé."""
    current = current.casefold()
    choices = []
    for event in upcoming_events(limit=25):
        label = f"{timezone.localtime(event.starts_at):%a %d/%m %H:%M} · {event.title}"
        if current in label.casefold():
            choices.append((label[:100], event.pk))
    return choices


def character_choices(discord_id: str, current: str) -> list[tuple[str, int]]:
    current = current.casefold()
    characters = Character.objects.filter(owner__discord_id=discord_id, owner__is_active=True).select_related(
        "player_class"
    )
    return [
        (f"{c.name} ({c.player_class.name} {c.level})", c.pk)
        for c in characters
        if current in c.name.casefold()
    ][:25]


def signup_from_discord(discord_id: str, event_id: int, character_id: int, role: str, status: str) -> str:
    """Inscrit le joueur et renvoie le message à afficher."""
    user = User.objects.filter(discord_id=discord_id, is_active=True).first()
    if not user:
        return f"Tu n'as pas encore de compte : connecte-toi d'abord sur {settings.SITE_URL}."
    event = Event.objects.filter(pk=event_id).first()
    if not event:
        return "Événement introuvable."
    if not event.signups_open:
        return "Les inscriptions sont closes pour cet événement."
    if role not in Role.values:
        return "Rôle inconnu."
    try:
        signup, created = event_services.upsert_signup(
            event, user, {"character": character_id, "role": role, "status": status}
        )
    except ValidationError as exc:
        detail = exc.detail
        message = next(iter(detail.values())) if isinstance(detail, dict) else detail
        if isinstance(message, list):
            message = message[0]
        return f"Inscription refusée : {message}"
    verb = "Inscrit" if created else "Inscription mise à jour"
    return (
        f"{verb} : **{signup.character.name}** en {Role(role).label} pour **{event.title}** "
        f"({discord_time(event.starts_at, 'f')}). {event_url(event)}"
    )
