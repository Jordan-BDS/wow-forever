"""Mise en file des notifications. Les textes sont rendus ici, en français, avec les horodatages Discord."""

from datetime import datetime

from django.conf import settings

from apps.accounts.models import User
from apps.events.models import Event, Placement, Signup, SignupStatus
from apps.polls.models import Poll

from .models import DM_PREFERENCE_FOR_KIND, Notification, NotificationKind


def site_url(path: str) -> str:
    return f"{settings.SITE_URL}{path}"


def discord_time(moment: datetime, style: str = "F") -> str:
    """Horodatage affiché dans le fuseau de chaque lecteur par Discord (F = date complète, R = relatif)."""
    return f"<t:{int(moment.timestamp())}:{style}>"


def wants_dm(user: User, kind: str) -> bool:
    if not user.is_active or not user.dm_enabled:
        return False
    preference = DM_PREFERENCE_FOR_KIND.get(NotificationKind(kind))
    return preference not in (user.dm_muted_kinds or [])


def notify_channel(kind: str, text: str) -> Notification:
    return Notification.objects.create(kind=kind, text=text)


def notify_user(user: User, kind: str, text: str) -> Notification | None:
    if not wants_dm(user, kind):
        return None
    return Notification.objects.create(kind=kind, recipient=user, text=text)


# --- événements -----------------------------------------------------------------


def _event_line(event: Event) -> str:
    return f"**{event.title}** — {discord_time(event.starts_at)} ({discord_time(event.starts_at, 'R')})"


def event_url(event: Event) -> str:
    return site_url(f"/agenda/{event.pk}")


def event_created(event: Event) -> Notification:
    text = (
        f"📅 Nouvel événement : {_event_line(event)}\n"
        f"Organisé par {event.organizer.display_name}"
        + (f" · niveau {event.min_level}+" if event.min_level else "")
        + f"\nInscriptions : {event_url(event)}"
    )
    return notify_channel(NotificationKind.EVENT_CREATED, text)


def event_cancelled(event: Event) -> Notification:
    text = f"❌ Événement annulé : {_event_line(event)}\n{event_url(event)}"
    return notify_channel(NotificationKind.EVENT_CANCELLED, text)


def event_rescheduled(event: Event, previous_start: datetime) -> Notification:
    text = (
        f"🕒 Événement déplacé : **{event.title}**\n"
        f"~~{discord_time(previous_start)}~~ → {discord_time(event.starts_at)} "
        f"({discord_time(event.starts_at, 'R')})\n{event_url(event)}"
    )
    return notify_channel(NotificationKind.EVENT_RESCHEDULED, text)


def composition_text(event: Event) -> str:
    lines = [f"🛡️ Composition de **{event.title}** — {discord_time(event.starts_at)}"]
    for role, label in (("tank", "Tanks"), ("heal", "Heals"), ("dps", "DPS")):
        confirmed = [s for s in event.signups.all() if s.role == role and s.placement == Placement.CONFIRMED]
        need = event.needs_for(role)
        count = f"{len(confirmed)}" + (f"/{need}" if need is not None else "")
        names = ", ".join(s.character.name for s in confirmed) or "—"
        lines.append(f"**{label}** ({count}) : {names}")
    bench = [s for s in event.signups.all() if s.placement == Placement.BENCH]
    if bench:
        lines.append("**Banc** : " + ", ".join(s.character.name for s in bench))
    lines.append(event_url(event))
    return "\n".join(lines)


def composition_announced(event: Event) -> Notification:
    return notify_channel(NotificationKind.COMPOSITION, composition_text(event))


def placement_changed(signup: Signup) -> Notification | None:
    event = signup.event
    if signup.placement == Placement.CONFIRMED:
        text = (
            f"✅ Tu es **confirmé** avec {signup.character.name} pour {_event_line(event)}\n"
            f"{event_url(event)}"
        )
    elif signup.placement == Placement.BENCH:
        text = (
            f"🪑 Tu es placé **sur le banc** avec {signup.character.name} pour {_event_line(event)}\n"
            f"Reste dispo au cas où. {event_url(event)}"
        )
    else:
        return None
    return notify_user(signup.user, NotificationKind.PLACEMENT, text)


def event_reminder(event: Event) -> list[Notification]:
    created = [
        notify_channel(
            NotificationKind.EVENT_REMINDER,
            f"⏰ Rappel : {_event_line(event)}\n{event_url(event)}",
        )
    ]
    for signup in event.signups.all():
        if signup.placement == Placement.CONFIRMED and signup.status != SignupStatus.ABSENT:
            dm = notify_user(
                signup.user,
                NotificationKind.EVENT_REMINDER,
                f"⏰ Rappel : tu es confirmé avec {signup.character.name} pour {_event_line(event)}\n"
                f"{event_url(event)}",
            )
            if dm:
                created.append(dm)
    return created


# --- sondages -------------------------------------------------------------------


def poll_url(poll: Poll) -> str:
    return site_url(f"/sondages/{poll.pk}")


def poll_opened(poll: Poll) -> Notification:
    text = (
        f"🗳️ Nouveau sondage : **{poll.title}**\n"
        f"Propositions jusqu'au {discord_time(poll.proposals_end)}, "
        f"votes jusqu'au {discord_time(poll.votes_end)}.\n"
        f"{poll_url(poll)}"
    )
    return notify_channel(NotificationKind.POLL_OPENED, text)


def poll_reminder(poll: Poll, phase: str) -> Notification:
    if phase == "proposals":
        text = (
            f"⏰ Dernières heures pour **proposer** dans « {poll.title} » : "
            f"clôture {discord_time(poll.proposals_end, 'R')}.\n{poll_url(poll)}"
        )
    else:
        text = (
            f"⏰ Dernières heures pour **voter** dans « {poll.title} » : "
            f"clôture {discord_time(poll.votes_end, 'R')}.\n{poll_url(poll)}"
        )
    return notify_channel(NotificationKind.POLL_REMINDER, text)


def poll_validated(poll: Poll) -> Notification:
    winner = poll.validated_proposal.text if poll.validated_proposal else "?"
    text = f"🏆 Résultat de « {poll.title} » : **{winner}**"
    if poll.sets_guild_name:
        text += "\nC'est le nouveau nom de la guilde !"
    if poll.validation_note:
        text += f"\n_{poll.validation_note}_"
    text += f"\n{poll_url(poll)}"
    return notify_channel(NotificationKind.POLL_VALIDATED, text)


# --- demandes de craft ------------------------------------------------------------


def craft_url(craft) -> str:
    return site_url(f"/crafts?demande={craft.pk}")


def craft_requested(craft) -> list[Notification]:
    label = f"**{craft.quantity} × {craft.recipe.name}**"
    created = [
        notify_channel(
            NotificationKind.CRAFT_REQUEST,
            f"🔨 Demande de craft : {label} pour {craft.requester.display_name}"
            + (f" (cible : {craft.target_character.name})" if craft.target_character else "")
            + f"\n{craft_url(craft)}",
        )
    ]
    if craft.target_character and craft.target_character.owner_id != craft.requester_id:
        dm = notify_user(
            craft.target_character.owner,
            NotificationKind.CRAFT_REQUEST,
            f"🔨 {craft.requester.display_name} te demande {label} avec {craft.target_character.name}.\n"
            f"{craft_url(craft)}",
        )
        if dm:
            created.append(dm)
    return created


def craft_updated(craft) -> Notification | None:
    label = f"**{craft.quantity} × {craft.recipe.name}**"
    if craft.status == "taken" and craft.crafter:
        who = f"{craft.crafter.name} ({craft.crafter.owner.display_name})"
        text = f"🔨 {who} prend en charge ta demande {label}."
    elif craft.status == "delivered":
        text = f"✅ Ta demande {label} est livrée."
    elif craft.status == "cancelled":
        if not craft.crafter:
            return None
        return notify_user(
            craft.crafter.owner, NotificationKind.CRAFT_UPDATE, f"❌ La demande {label} a été annulée."
        )
    else:
        return None
    return notify_user(craft.requester, NotificationKind.CRAFT_UPDATE, f"{text}\n{craft_url(craft)}")
