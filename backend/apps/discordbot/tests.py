from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.characters.models import Character
from apps.discordbot import services
from apps.events.models import Event, Signup
from apps.gamedata.models import PlayerClass, Race
from apps.gamedata.seed import seed
from apps.notifications.models import Notification, NotificationStatus

pytestmark = pytest.mark.django_db

NOW = timezone.now()


@pytest.fixture
def event(db, officer):
    seed()
    return Event.objects.create(
        title="Mortemines", kind="dungeon", starts_at=NOW + timedelta(days=1), organizer=officer, max_size=5
    )


@pytest.fixture
def character(member):
    return Character.objects.create(
        owner=member,
        name="Thrall",
        player_class=PlayerClass.objects.get(slug="shaman"),
        race=Race.objects.get(slug="orc"),
        level=60,
        main_role="heal",
        off_role="dps",
        is_main=True,
    )


def test_bot_module_imports_and_builds_commands():
    from apps.discordbot import bot

    assert bot.events_command.name == "events"
    assert bot.signup_command.name == "inscription"
    assert {c.value for c in bot.ROLE_CHOICES} == {"tank", "heal", "dps"}


class TestOutbox:
    def test_pending_then_sent(self):
        n = Notification.objects.create(kind="event_created", text="x")
        assert services.pending_notifications() == [n]
        services.mark_sent(n)
        n.refresh_from_db()
        assert n.status == NotificationStatus.SENT and n.sent_at and n.attempts == 1
        assert services.pending_notifications() == []

    def test_failures_retry_then_give_up(self):
        n = Notification.objects.create(kind="event_created", text="x")
        services.mark_failed(n, "boom")
        services.mark_failed(n, "boom")
        assert n.status == NotificationStatus.PENDING
        assert services.pending_notifications() == [n]
        services.mark_failed(n, "boom")
        assert n.status == NotificationStatus.FAILED
        assert services.pending_notifications() == []

    def test_channel_id_parsing(self):
        from apps.guild.models import GuildSettings

        assert services.announcement_channel_id() is None
        s = GuildSettings.load()
        s.discord_channel_id = "123456789"
        s.save()
        assert services.announcement_channel_id() == 123456789


class TestAccess:
    def test_has_allowed_role(self):
        assert services.has_allowed_role(["role-member", "other"])
        assert not services.has_allowed_role(["other"])

    def test_revoke_access_deactivates_with_discord_reason(self, member):
        assert services.revoke_access(member.discord_id, "test") is True
        member.refresh_from_db()
        assert not member.is_active and member.deactivation_reason == "discord"
        assert services.revoke_access(member.discord_id, "test") is False
        assert services.revoke_access("unknown", "test") is False


class TestSlashCommands:
    def test_upcoming_events_text(self, event):
        text = services.upcoming_events_text()
        assert "Mortemines" in text and f"/agenda/{event.pk}" in text
        Event.objects.all().delete()
        assert "Rien de prévu" in services.upcoming_events_text()

    def test_event_and_character_choices(self, event, character, member):
        assert services.event_choices("morte") == [(services.event_choices("")[0][0], event.pk)]
        assert services.event_choices("zzz") == []
        assert services.character_choices(member.discord_id, "thr") == [("Thrall (Chaman 60)", character.pk)]
        assert services.character_choices("nobody", "") == []

    def test_signup_from_discord_happy_path_and_update(self, event, character, member):
        message = services.signup_from_discord(member.discord_id, event.pk, character.pk, "heal", "present")
        assert message.startswith("Inscrit")
        assert Signup.objects.get(event=event, user=member).role == "heal"
        message = services.signup_from_discord(member.discord_id, event.pk, character.pk, "dps", "maybe")
        assert message.startswith("Inscription mise à jour")
        assert Signup.objects.get(event=event, user=member).status == "maybe"

    def test_signup_from_discord_errors(self, event, character, member):
        assert "pas encore de compte" in services.signup_from_discord(
            "999", event.pk, character.pk, "heal", "present"
        )
        assert "introuvable" in services.signup_from_discord(
            member.discord_id, 9999, character.pk, "heal", "present"
        )
        refused = services.signup_from_discord(member.discord_id, event.pk, character.pk, "tank", "present")
        assert refused.startswith("Inscription refusée")
        event.signup_deadline = NOW - timedelta(minutes=1)
        event.save()
        assert "closes" in services.signup_from_discord(
            member.discord_id, event.pk, character.pk, "heal", "present"
        )

    def test_unknown_discord_user_cannot_sign_up_other_people(self, event, character):
        User.objects.create_user("777")
        assert "refusée" in services.signup_from_discord("777", event.pk, character.pk, "heal", "present")
