"""
Logique synchrone du bot (ORM, règles métier). Le bot l'appelle via `sync_to_async`,
ce qui permet de la tester sans Discord.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import DeactivationReason, User
from apps.accounts.services import deactivate_user
from apps.characters.models import Character
from apps.events import services as event_services
from apps.events.models import Event, EventKind, EventStatus, SignupStatus
from apps.gamedata.models import Role
from apps.guild.models import GuildSettings
from apps.notifications import services as notify
from apps.notifications.models import (
    CHANNEL_FIELD_FOR_KIND,
    Notification,
    NotificationKind,
    NotificationStatus,
)
from apps.notifications.services import discord_time, event_url
from apps.polls.models import Poll

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


# --- outbox ------------------------------------------------------------------------


def pending_notifications(limit: int = 20) -> list[Notification]:
    return list(
        Notification.objects.filter(status=NotificationStatus.PENDING, attempts__lt=MAX_ATTEMPTS)
        .select_related("recipient", "event")
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


def _channel_id(raw: str) -> int | None:
    return int(raw) if raw and raw.isdigit() else None


def announcement_channel_id() -> int | None:
    """Le salon général (secours)."""
    return _channel_id(GuildSettings.load().discord_channel_id)


def channel_id_for(kind: str) -> int | None:
    """Salon où publier ce type de message : le salon dédié s'il est renseigné, sinon le salon général."""
    stored = GuildSettings.load()
    field = CHANNEL_FIELD_FOR_KIND.get(kind)
    dedicated = _channel_id(getattr(stored, field)) if field else None
    return dedicated if dedicated is not None else _channel_id(stored.discord_channel_id)


# --- accès -----------------------------------------------------------------------------


def has_allowed_role(role_ids: list[str]) -> bool:
    from apps.guild.config import discord_config

    return bool(set(discord_config().allowed_role_ids) & set(role_ids))


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


def craft_search_text(query: str) -> str:
    """Réponse de /craft : recettes correspondantes et personnages qui les connaissent."""
    from django.db.models import Q

    from apps.gamedata.models import Recipe

    query = query.strip()
    if len(query) < 2:
        return "Donne au moins deux lettres du nom d'une recette ou d'un objet."
    recipes = (
        Recipe.objects.filter(
            Q(name__icontains=query)
            | Q(product__name__icontains=query)
            | Q(product__name_en__icontains=query)
        )
        .select_related("profession")
        .prefetch_related("known_by__character__owner", "known_by__character__professions")[:8]
    )
    lines = []
    for recipe in recipes:
        crafters = [
            f"{k.character.name} ({k.character.owner.display_name})"
            for k in recipe.known_by.all()
            if k.character.owner.is_active
        ]
        who = ", ".join(crafters) if crafters else "personne pour l'instant"
        lines.append(f"• **{recipe.name}** ({recipe.profession.name} {recipe.min_skill}) : {who}")
    if not lines:
        return f"Aucune recette ne correspond à « {query} »."
    return "\n".join(lines) + f"\n{settings.SITE_URL}/crafts?q={query}"


# --- synchronisation des événements -----------------------------------------------------
#
# Le site met en file une demande `event_sync` à chaque changement d'un événement ou de ses inscrits ;
# le bot la dépile, crée ou met à jour l'événement planifié Discord (onglet « Événements ») et le message
# d'inscription du salon. Dans l'autre sens, les événements créés / modifiés / supprimés dans l'onglet
# Discord arrivent ici via les fonctions `*_from_discord`.


@dataclass(frozen=True)
class EventSnapshot:
    """État d'un événement tel que le bot doit le refléter côté Discord."""

    id: int
    status: str  # planned / cancelled / done
    name: str
    description: str
    location: str | None
    starts_at: datetime
    ends_at: datetime
    signups_open: bool
    discord_event_id: str
    discord_message_id: str
    message_text: str

    @property
    def planned(self) -> bool:
        return self.status == EventStatus.PLANNED

    def differs_from(
        self, name: str, description: str | None, starts_at: datetime, ends_at: datetime | None
    ) -> bool:
        """Compare à l'état Discord, aux arrondis près (secondes tronquées, None si description vide)."""
        return (
            name != self.name
            or (description or "") != self.description
            or int(starts_at.timestamp()) != int(self.starts_at.timestamp())
            or ends_at is None
            or int(ends_at.timestamp()) != int(self.ends_at.timestamp())
        )


def _event_queryset():
    return Event.objects.select_related("organizer", "instance").prefetch_related(
        "signups__character", "signups__user"
    )


def event_snapshot(event_id: int) -> EventSnapshot | None:
    event = _event_queryset().filter(pk=event_id).first()
    if event is None:
        return None
    return EventSnapshot(
        id=event.pk,
        status=event.effective_status,
        name=notify.discord_event_name(event),
        description=notify.discord_event_description(event),
        location=notify.discord_event_location(event),
        starts_at=event.starts_at,
        ends_at=event.effective_ends_at,
        signups_open=event.signups_open,
        discord_event_id=event.discord_event_id,
        discord_message_id=event.discord_message_id,
        message_text=notify.signup_message_text(event),
    )


def store_discord_ids(
    event_id: int, *, discord_event_id: str | None = None, discord_message_id: str | None = None
):
    """Mémorise les identifiants Discord ("" pour effacer). Ne touche pas à `updated_at`."""
    fields = {}
    if discord_event_id is not None:
        fields["discord_event_id"] = discord_event_id
    if discord_message_id is not None:
        fields["discord_message_id"] = discord_message_id
    if fields:
        Event.objects.filter(pk=event_id).update(**fields)


def complete_event_syncs(event_id: int) -> int:
    """Marque envoyées toutes les demandes de synchronisation en attente pour cet événement."""
    return Notification.objects.filter(
        kind=NotificationKind.EVENT_SYNC, event_id=event_id, status=NotificationStatus.PENDING
    ).update(status=NotificationStatus.SENT, sent_at=timezone.now())


def event_by_discord_id(discord_event_id: int | str) -> Event | None:
    return _event_queryset().filter(discord_event_id=str(discord_event_id)).first()


def _default_end(starts_at: datetime, ends_at: datetime | None) -> datetime | None:
    if ends_at is None or ends_at <= starts_at:
        return None
    return ends_at


def create_event_from_discord(
    discord_event_id: int | str,
    creator_discord_id: int | str | None,
    name: str,
    description: str | None,
    starts_at: datetime,
    ends_at: datetime | None,
) -> Event | None:
    """Un membre a créé un événement dans l'onglet Discord : on le reflète sur le site, lui en organisateur.

    Renvoie None si le créateur n'a pas de compte actif sur le site (l'événement Discord est alors ignoré),
    ou l'événement existant si cet identifiant Discord est déjà connu (réception en double).
    """
    existing = event_by_discord_id(discord_event_id)
    if existing:
        return existing
    organizer = User.objects.filter(discord_id=str(creator_discord_id or ""), is_active=True).first()
    if organizer is None:
        logger.info(
            "Événement Discord %s ignoré : créateur %s sans compte", discord_event_id, creator_discord_id
        )
        return None
    event = Event.objects.create(
        title=(name or "Événement").strip()[:120],
        kind=EventKind.SOCIAL,
        starts_at=starts_at,
        ends_at=_default_end(starts_at, ends_at),
        description=notify.strip_discord_event_link(description or ""),
        organizer=organizer,
        created_by=organizer,
        discord_event_id=str(discord_event_id),
    )
    notify.event_sync(event)
    return event


def update_event_from_discord(
    discord_event_id: int | str,
    name: str,
    description: str | None,
    starts_at: datetime,
    ends_at: datetime | None,
) -> Event | None:
    """Reflète une modification faite dans l'onglet Discord. Renvoie l'événement s'il a changé, sinon None.

    Les modifications écrites par le bot lui-même reviennent en écho par la gateway : elles sont
    identiques à l'état en base et donc ignorées ici, ce qui coupe toute boucle.
    """
    event = event_by_discord_id(discord_event_id)
    if event is None or event.status != EventStatus.PLANNED:
        return None
    snapshot = event_snapshot(event.pk)
    if not snapshot.differs_from(name, description, starts_at, ends_at):
        return None
    previous_start = event.starts_at
    if name != snapshot.name:
        event.title = name.strip()[:120] or event.title
    if (description or "") != snapshot.description:
        event.description = notify.strip_discord_event_link(description or "")
    event.starts_at = starts_at
    if ends_at is not None:
        # Discord a toujours une fin explicite : on la garde telle quelle (la fin par défaut du site
        # suit le début, pas celle de Discord).
        event.ends_at = _default_end(starts_at, ends_at)
    if event.signup_deadline and event.signup_deadline > event.starts_at:
        event.signup_deadline = None
    event.save()
    if int(event.starts_at.timestamp()) != int(previous_start.timestamp()):
        notify.event_rescheduled(event, previous_start)
    notify.event_sync(event)
    return event


def cancel_event_from_discord(discord_event_id: int | str) -> Event | None:
    """L'événement a été annulé ou supprimé côté Discord : on l'annule sur le site (l'historique reste)."""
    event = event_by_discord_id(discord_event_id)
    if event is None:
        return None
    event.discord_event_id = ""
    if event.status == EventStatus.PLANNED and event.effective_status == EventStatus.PLANNED:
        event.status = EventStatus.CANCELLED
        event.save(update_fields=["status", "discord_event_id", "updated_at"])
        notify.event_cancelled(event)
    else:
        event.save(update_fields=["discord_event_id"])
    notify.event_sync(event)
    return event


# --- boutons d'inscription ----------------------------------------------------------------

QUICK_STATUSES = {
    "present": "Présent",
    "maybe": "Peut-être",
    "late": "En retard",
    "absent": "Absent",
}


def _signup_error(exc: ValidationError) -> str:
    detail = exc.detail
    message = next(iter(detail.values())) if isinstance(detail, dict) else detail
    if isinstance(message, list):
        message = message[0]
    return f"Inscription refusée : {message}"


def _signup_done(signup, created: bool) -> str:
    verb = "Inscrit" if created else "Inscription mise à jour"
    return (
        f"{verb} : **{signup.character.name}** en {Role(signup.role).label}, "
        f"{SignupStatus(signup.status).label.lower()} pour **{signup.event.title}**."
    )


def signup_choices(user: User, event: Event) -> list[tuple[str, str]]:
    """(libellé, "id_perso:rôle") pour chaque combinaison perso / rôle possible du joueur sur l'événement."""
    choices = []
    for character in user.characters.select_related("player_class").order_by("-is_main", "-level", "name"):
        if event.min_level and character.level < event.min_level:
            continue
        for role in (character.main_role, character.off_role):
            if role:
                label = (
                    f"{character.name} ({character.player_class.name} {character.level}) — {Role(role).label}"
                )
                choices.append((label[:100], f"{character.pk}:{role}"))
    return choices[:25]


def quick_signup(discord_id: str, event_id: int, status: str) -> tuple[str, list[tuple[str, str]] | None]:
    """Clic sur un bouton du message d'inscription.

    Renvoie (message, None) quand c'est réglé, ou (question, choix) quand il faut que le joueur
    précise son personnage et son rôle (première inscription avec plusieurs possibilités).
    """
    user = User.objects.filter(discord_id=discord_id, is_active=True).first()
    if not user:
        return f"Tu n'as pas encore de compte : connecte-toi d'abord sur {settings.SITE_URL}.", None
    event = Event.objects.filter(pk=event_id).select_related("organizer").first()
    if not event:
        return "Événement introuvable.", None
    if not event.signups_open:
        return "Les inscriptions sont closes pour cet événement.", None
    if status == "leave":
        removed = event_services.remove_signup(event, user)
        return ("Tu es désinscrit." if removed else "Tu n'étais pas inscrit."), None
    if status not in QUICK_STATUSES:
        return "Statut inconnu.", None

    current = event.signups.filter(user=user).select_related("character").first()
    if current:
        data = {
            "character": current.character_id,
            "role": current.role,
            "status": status,
            "comment": current.comment,
        }
        try:
            signup, created = event_services.upsert_signup(event, user, data)
        except ValidationError as exc:
            return _signup_error(exc), None
        return _signup_done(signup, created), None

    choices = signup_choices(user, event)
    if not choices:
        if not user.characters.exists():
            return f"Ajoute d'abord un personnage sur {settings.SITE_URL}/personnages.", None
        return f"Aucun de tes personnages n'a le niveau {event.min_level} requis.", None
    if len(choices) == 1:
        return signup_with_choice(discord_id, event_id, status, choices[0][1]), None
    return f"Avec quel personnage et quel rôle pour **{event.title}** ?", choices


def signup_with_choice(discord_id: str, event_id: int, status: str, choice: str) -> str:
    """Le joueur a choisi « perso:rôle » dans le menu : inscription effective."""
    try:
        character_id, role = choice.split(":")
        character_id = int(character_id)
    except ValueError:
        return "Choix invalide."
    return signup_from_discord(discord_id, event_id, character_id, role, status)


# --- synchronisation des sondages -------------------------------------------------------------


@dataclass(frozen=True)
class PollSnapshot:
    id: int
    status: str
    discord_message_id: str
    message_text: str


def poll_snapshot(poll_id: int) -> PollSnapshot | None:
    poll = Poll.objects.filter(pk=poll_id).select_related("validated_proposal", "cancelled_by").first()
    if poll is None:
        return None
    return PollSnapshot(
        id=poll.pk,
        status=poll.status,
        discord_message_id=poll.discord_message_id,
        message_text=notify.poll_message_text(poll),
    )


def store_poll_message(poll_id: int, message_id: str, status: str) -> None:
    Poll.objects.filter(pk=poll_id).update(discord_message_id=message_id, discord_synced_status=status)


def complete_poll_syncs(poll_id: int) -> int:
    return Notification.objects.filter(
        kind=NotificationKind.POLL_SYNC, poll_id=poll_id, status=NotificationStatus.PENDING
    ).update(status=NotificationStatus.SENT, sent_at=timezone.now())
