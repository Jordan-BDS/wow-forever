"""Rappels planifiés : scrutés périodiquement par le bot, idempotents grâce aux marqueurs sur les objets."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.events.models import Event, EventStatus
from apps.guild.models import GuildSettings
from apps.polls.models import Poll

from . import services

POLL_REMINDER_LEAD = timedelta(hours=24)


def scan_due_reminders(now=None) -> int:
    """Crée les notifications de rappel dues et renvoie leur nombre."""
    now = now or timezone.now()
    created = 0
    lead = timedelta(minutes=GuildSettings.load().reminder_minutes)

    due_events = (
        Event.objects.filter(
            status=EventStatus.PLANNED,
            reminder_sent_at__isnull=True,
            starts_at__gt=now,
            starts_at__lte=now + lead,
        )
        .select_related("organizer")
        .prefetch_related("signups__user", "signups__character")
    )
    for event in due_events:
        with transaction.atomic():
            created += len(services.event_reminder(event))
            event.reminder_sent_at = now
            event.save(update_fields=["reminder_sent_at"])

    open_polls = Poll.objects.filter(validated_proposal__isnull=True)
    for poll in open_polls.filter(
        proposals_reminder_sent=False, proposals_end__gt=now, proposals_end__lte=now + POLL_REMINDER_LEAD
    ):
        with transaction.atomic():
            services.poll_reminder(poll, "proposals")
            poll.proposals_reminder_sent = True
            poll.save(update_fields=["proposals_reminder_sent"])
            created += 1
    for poll in open_polls.filter(
        votes_reminder_sent=False, votes_end__gt=now, votes_end__lte=now + POLL_REMINDER_LEAD
    ):
        with transaction.atomic():
            services.poll_reminder(poll, "votes")
            poll.votes_reminder_sent = True
            poll.save(update_fields=["votes_reminder_sent"])
            created += 1
    return created
