from datetime import timedelta

import pytest
from django.utils import timezone

from apps.characters.models import Character
from apps.events.models import Event, Placement, Signup
from apps.gamedata.models import PlayerClass, Race
from apps.gamedata.seed import seed
from apps.guild.models import GuildSettings
from apps.notifications import services
from apps.notifications.models import Notification, NotificationKind
from apps.notifications.reminders import scan_due_reminders
from apps.polls.models import Poll

pytestmark = pytest.mark.django_db

NOW = timezone.now()


@pytest.fixture
def event(db, officer, member):
    seed()
    event = Event.objects.create(
        title="Cœur du Magma",
        kind="raid",
        starts_at=NOW + timedelta(minutes=45),
        organizer=officer,
        need_tanks=4,
        min_level=58,
    )
    character = Character.objects.create(
        owner=member,
        name="Thrall",
        player_class=PlayerClass.objects.get(slug="warrior"),
        race=Race.objects.get(slug="orc"),
        level=60,
        main_role="tank",
        is_main=True,
    )
    Signup.objects.create(
        event=event, user=member, character=character, role="tank", placement=Placement.CONFIRMED
    )
    return event


class TestEnqueue:
    def test_event_created_goes_to_channel_with_link_and_discord_timestamp(self, event):
        notification = services.event_created(event)
        assert notification.recipient is None
        assert notification.status == "pending"
        assert "Cœur du Magma" in notification.text
        assert f"<t:{int(event.starts_at.timestamp())}:F>" in notification.text
        assert f"/agenda/{event.pk}" in notification.text
        assert "niveau 58+" in notification.text

    def test_placement_dm_respects_preferences(self, event, member):
        signup = event.signups.get()
        assert services.placement_changed(signup).recipient == member
        member.dm_muted_kinds = ["placement"]
        member.save()
        assert services.placement_changed(Signup.objects.get(pk=signup.pk)) is None
        member.dm_muted_kinds = []
        member.dm_enabled = False
        member.save()
        assert services.placement_changed(Signup.objects.get(pk=signup.pk)) is None
        assert Notification.objects.filter(recipient=member).count() == 1

    def test_unplaced_does_not_dm(self, event):
        signup = event.signups.get()
        signup.placement = Placement.UNPLACED
        signup.save()
        assert services.placement_changed(Signup.objects.get(pk=signup.pk)) is None

    def test_composition_text_lists_confirmed_by_role(self, event):
        text = services.composition_text(event)
        assert "**Tanks** (1/4) : Thrall" in text
        assert "**Heals** (0) : —" in text

    def test_poll_validated_mentions_guild_name(self, officer, member):
        poll = Poll.objects.create(
            title="Nom", proposals_end=NOW, votes_end=NOW, sets_guild_name=True, created_by=officer
        )
        poll.validated_proposal = poll.proposals.create(author=member, text="Les Potes")
        poll.save()
        text = services.poll_validated(poll).text
        assert "**Les Potes**" in text
        assert "nouveau nom de la guilde" in text


class TestReminders:
    def test_event_reminder_fires_once_within_lead_time(self, event, member):
        settings = GuildSettings.load()
        settings.reminder_minutes = 60
        settings.save()
        assert scan_due_reminders(NOW) == 2  # salon + MP du confirmé
        kinds = list(Notification.objects.values_list("kind", "recipient_id"))
        assert (NotificationKind.EVENT_REMINDER, None) in kinds
        assert (NotificationKind.EVENT_REMINDER, member.pk) in kinds
        assert scan_due_reminders(NOW) == 0
        event.refresh_from_db()
        assert event.reminder_sent_at is not None

    def test_event_outside_lead_time_or_cancelled_is_skipped(self, event):
        settings = GuildSettings.load()
        settings.reminder_minutes = 30
        settings.save()
        assert scan_due_reminders(NOW) == 0
        settings.reminder_minutes = 60
        settings.save()
        event.status = "cancelled"
        event.save()
        assert scan_due_reminders(NOW) == 0

    def test_poll_reminders_each_phase_once(self, officer):
        Poll.objects.create(
            title="Nom",
            proposals_end=NOW + timedelta(hours=10),
            votes_end=NOW + timedelta(hours=20),
            created_by=officer,
        )
        assert scan_due_reminders(NOW) == 2
        assert scan_due_reminders(NOW) == 0
        texts = list(Notification.objects.values_list("text", flat=True))
        assert any("proposer" in t for t in texts) and any("voter" in t for t in texts)

    def test_poll_reminder_not_sent_too_early(self, officer):
        Poll.objects.create(
            title="Nom",
            proposals_end=NOW + timedelta(days=3),
            votes_end=NOW + timedelta(days=6),
            created_by=officer,
        )
        assert scan_due_reminders(NOW) == 0


class TestDiscordSync:
    def test_event_sync_is_deduplicated_while_pending(self, event):
        first = services.event_sync(event)
        assert services.event_sync(event) == first
        assert first.kind == NotificationKind.EVENT_SYNC and first.event == event and first.recipient is None
        first.status = "sent"
        first.save()
        assert services.event_sync(event) != first

    def test_discord_description_round_trip(self, event):
        event.description = "Venez avec vos potions."
        rendered = services.discord_event_description(event)
        assert rendered.startswith("Venez avec vos potions.\n\nInscriptions : ")
        assert f"/agenda/{event.pk}" in rendered
        assert services.strip_discord_event_link(rendered) == "Venez avec vos potions."
        event.description = ""
        assert services.strip_discord_event_link(services.discord_event_description(event)) == ""
        event.description = "x" * 2000
        assert len(services.discord_event_description(event)) <= services.DISCORD_EVENT_DESCRIPTION_MAX

    def test_discord_name_and_location(self, event):
        from apps.gamedata.models import Instance

        event.title = "t" * 150
        assert len(services.discord_event_name(event)) == 100
        assert services.discord_event_location(event) is None
        event.instance = Instance.objects.get(slug="molten-core")
        assert services.discord_event_location(event) == event.instance.name

    def test_signup_message_lists_signups_by_role_and_state(self, event, other_member):
        other = Character.objects.create(
            owner=other_member,
            name="Jaina",
            player_class=PlayerClass.objects.get(slug="mage"),
            race=Race.objects.get(slug="human"),
            level=60,
            main_role="dps",
        )
        Signup.objects.create(event=event, user=other_member, character=other, role="dps", status="maybe")
        text = services.signup_message_text(event)
        assert "**Tanks** (1/4) : ✅ Thrall" in text
        assert "**DPS** (0) : —" in text
        assert "Peut-être : Jaina" in text
        assert "1 inscrits" in text and "niveau 58+" in text
        assert "boutons ci-dessous" in text and f"/agenda/{event.pk}" in text
        assert len(text) <= services.DISCORD_MESSAGE_MAX

    def test_signup_message_for_cancelled_event_has_no_buttons_hint(self, event):
        event.status = "cancelled"
        text = services.signup_message_text(event)
        assert text.startswith("❌") and "Annulé" in text
        assert "boutons" not in text


class TestDiscordCleanup:
    def _cleanups(self):
        return list(Notification.objects.filter(kind=NotificationKind.DISCORD_CLEANUP))

    def test_deleting_an_event_queues_cleanup_of_its_discord_traces(self, event, as_user, officer):
        settings = GuildSettings.load()
        settings.discord_channel_id = "1"
        settings.discord_agenda_channel_id = "42"
        settings.save()
        Event.objects.filter(pk=event.pk).update(discord_event_id="777", discord_message_id="888")
        services.event_sync(event)  # une synchro en attente disparaît avec l'événement
        event.refresh_from_db()

        assert as_user(officer).delete(f"/api/events/{event.pk}/").status_code == 204

        (cleanup,) = self._cleanups()
        assert cleanup.payload == {"scheduled_event_id": "777", "channel_id": "42", "message_id": "888"}
        assert cleanup.event is None and cleanup.recipient is None and "Cœur du Magma" in cleanup.text
        assert not Notification.objects.filter(kind=NotificationKind.EVENT_SYNC).exists()

    def test_nothing_queued_when_discord_never_heard_of_it(self, event):
        event.delete()
        assert self._cleanups() == []

    def test_deleting_a_poll_removes_its_follow_up_message(self, officer, as_user):
        GuildSettings.objects.update_or_create(pk=1, defaults={"discord_channel_id": "5"})
        poll = Poll.objects.create(
            title="Nom de guilde",
            proposals_end=NOW + timedelta(days=1),
            votes_end=NOW + timedelta(days=2),
            created_by=officer,
            discord_message_id="999",
        )
        assert as_user(officer).delete(f"/api/polls/{poll.pk}/").status_code == 204
        (cleanup,) = self._cleanups()
        assert cleanup.payload == {"channel_id": "5", "message_id": "999"}  # secours : salon général
