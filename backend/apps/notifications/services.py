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


def event_sync(event: Event) -> Notification:
    """Demande au bot de resynchroniser l'événement avec Discord (événement planifié + message d'inscription).

    Dédupliquée : une seule demande en attente par événement, quel que soit le nombre de changements.
    """
    pending = Notification.objects.filter(
        kind=NotificationKind.EVENT_SYNC, event=event, status="pending"
    ).first()
    if pending:
        return pending
    return Notification.objects.create(
        kind=NotificationKind.EVENT_SYNC, event=event, text=f"Synchronisation Discord de « {event.title} »"
    )


# Limites Discord pour un événement planifié.
DISCORD_EVENT_NAME_MAX = 100
DISCORD_EVENT_DESCRIPTION_MAX = 1000
DISCORD_MESSAGE_MAX = 2000


def discord_event_name(event: Event) -> str:
    return event.title[:DISCORD_EVENT_NAME_MAX]


def discord_event_description(event: Event) -> str:
    """Description de l'événement Discord : la description du site suivie du lien vers la fiche."""
    link = f"Inscriptions : {event_url(event)}"
    room = DISCORD_EVENT_DESCRIPTION_MAX - len(link) - 2
    description = event.description.strip()
    if len(description) > room:
        description = description[: room - 1].rstrip() + "…"
    return f"{description}\n\n{link}" if description else link


def strip_discord_event_link(description: str) -> str:
    """Inverse de `discord_event_description` : retire la ligne de lien ajoutée par le bot."""
    lines = description.rstrip().splitlines()
    if lines and lines[-1].startswith("Inscriptions : ") and settings.SITE_URL in lines[-1]:
        lines = lines[:-1]
    return "\n".join(lines).strip()


def discord_event_location(event: Event) -> str | None:
    """Lieu affiché par Discord : l'instance ciblée ; None = ne pas toucher au lieu saisi côté Discord."""
    return event.instance.name if event.instance else None


def signup_message_text(event: Event) -> str:
    """Message d'inscription publié dans le salon : état de l'événement et inscrits par rôle, tenu à jour.

    Les boutons d'inscription sont ajoutés par le bot ; ce texte en est le corps.
    """
    status = event.effective_status
    header = f"📅 {_event_line(event)}"
    if status == "cancelled":
        header = f"❌ ~~{event.title}~~ — **Annulé**"
    elif status == "done":
        header = f"✔️ {_event_line(event)} — terminé"

    details = [event.get_kind_display() + (f" · {event.instance.name}" if event.instance else "")]
    details.append(f"Organisé par {event.organizer.display_name}")
    if event.min_level:
        details.append(f"niveau {event.min_level}+")
    signups = list(event.signups.all())
    coming = [s for s in signups if s.status in (SignupStatus.PRESENT, SignupStatus.LATE)]
    details.append(f"{len(coming)}" + (f"/{event.max_size}" if event.max_size else "") + " inscrits")

    lines = [header, " · ".join(details)]
    if event.description.strip():
        description = event.description.strip()
        lines.append(description[:300].rstrip() + ("…" if len(description) > 300 else ""))
    lines.append("")
    for role, label in (("tank", "Tanks"), ("heal", "Heals"), ("dps", "DPS")):
        by_role = [s for s in coming if s.role == role]
        need = event.needs_for(role)
        count = f"{len(by_role)}" + (f"/{need}" if need is not None else "")
        names = ", ".join(
            ("✅ " if s.placement == Placement.CONFIRMED else "")
            + s.character.name
            + (" (en retard)" if s.status == SignupStatus.LATE else "")
            for s in by_role
        )
        lines.append(f"**{label}** ({count}) : {names or '—'}")
    maybe = [s for s in signups if s.status == SignupStatus.MAYBE]
    absent = [s for s in signups if s.status == SignupStatus.ABSENT]
    if maybe:
        lines.append("🤔 Peut-être : " + ", ".join(s.character.name for s in maybe))
    if absent:
        lines.append("🚫 Absents : " + ", ".join(s.character.name for s in absent))
    lines.append("")
    if status != "planned":
        lines.append(event_url(event))
    elif event.signups_open:
        deadline = event.signup_deadline or event.starts_at
        lines.append(
            f"Inscris-toi avec les boutons ci-dessous (clôture {discord_time(deadline, 'f')})"
            f" · {event_url(event)}"
        )
    else:
        lines.append(f"Inscriptions closes · {event_url(event)}")
    text = "\n".join(lines)
    if len(text) > DISCORD_MESSAGE_MAX:
        text = text[: DISCORD_MESSAGE_MAX - 1] + "…"
    return text


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
