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


# --- synchronisation des événements ---------------------------------------------------------


@pytest.fixture
def mirrored(event):
    Event.objects.filter(pk=event.pk).update(discord_event_id="555", discord_message_id="999")
    event.refresh_from_db()
    return event


class TestEventSnapshot:
    def test_snapshot_reflects_site_state(self, mirrored, character, member):
        Signup.objects.create(event=mirrored, user=member, character=character, role="heal")
        snap = services.event_snapshot(mirrored.pk)
        assert snap.planned and snap.signups_open
        assert (
            snap.name == "Mortemines" and snap.discord_event_id == "555" and snap.discord_message_id == "999"
        )
        assert snap.ends_at == mirrored.starts_at + timedelta(hours=3)
        assert "**Heals** (1) : Thrall" in snap.message_text
        assert f"/agenda/{mirrored.pk}" in snap.description
        assert services.event_snapshot(10_000) is None

    def test_differs_from_ignores_rounding_and_echoes(self, mirrored):
        snap = services.event_snapshot(mirrored.pk)
        same = snap.starts_at.replace(microsecond=0)
        assert not snap.differs_from(snap.name, snap.description, same, snap.ends_at)
        assert snap.differs_from("Autre", snap.description, snap.starts_at, snap.ends_at)
        assert snap.differs_from(
            snap.name, snap.description, snap.starts_at + timedelta(hours=1), snap.ends_at
        )
        assert snap.differs_from(snap.name, snap.description, snap.starts_at, None)

    def test_store_ids_and_complete_syncs(self, event):
        services.store_discord_ids(event.pk, discord_event_id="1", discord_message_id="2")
        event.refresh_from_db()
        assert (event.discord_event_id, event.discord_message_id) == ("1", "2")
        services.store_discord_ids(event.pk, discord_event_id="")
        event.refresh_from_db()
        assert (event.discord_event_id, event.discord_message_id) == ("", "2")
        Notification.objects.create(kind="event_sync", event=event, text="a")
        Notification.objects.create(kind="event_sync", event=event, text="b")
        assert services.complete_event_syncs(event.pk) == 2
        assert not Notification.objects.filter(status=NotificationStatus.PENDING).exists()


class TestFromDiscord:
    START = NOW + timedelta(days=2)

    def test_create_requires_known_creator_and_is_idempotent(self, member, db):
        seed()
        assert services.create_event_from_discord(1, "nobody", "Soirée", "", self.START, None) is None
        event = services.create_event_from_discord(
            1, member.discord_id, "Soirée pêche", "On pêche.\n\nInscriptions : http://x", self.START, None
        )
        assert event.organizer == member and event.created_by == member
        assert event.kind == "social" and event.instance is None and event.discord_event_id == "1"
        assert event.description == "On pêche.\n\nInscriptions : http://x"  # lien d'un autre site : conservé
        assert Notification.objects.filter(kind="event_sync", event=event).count() == 1
        assert (
            services.create_event_from_discord(1, member.discord_id, "Doublon", "", self.START, None) == event
        )
        assert Event.objects.count() == 1

    def test_create_strips_our_link_and_keeps_end(self, member, db, settings):
        seed()
        description = f"Détails\n\nInscriptions : {settings.SITE_URL}/agenda/12"
        event = services.create_event_from_discord(
            2, member.discord_id, "x" * 150, description, self.START, self.START + timedelta(hours=2)
        )
        assert event.description == "Détails" and len(event.title) == 120
        assert event.ends_at == self.START + timedelta(hours=2)

    def test_update_ignores_echo_and_applies_real_changes(self, mirrored):
        snap = services.event_snapshot(mirrored.pk)
        assert (
            services.update_event_from_discord(555, snap.name, snap.description, snap.starts_at, snap.ends_at)
            is None
        )
        assert not Notification.objects.exists()

        new_start = snap.starts_at + timedelta(hours=2)
        event = services.update_event_from_discord(
            555, "Mortemines HM", "Nouvelle consigne", new_start, new_start + timedelta(hours=1)
        )
        assert event.title == "Mortemines HM" and event.description == "Nouvelle consigne"
        assert event.starts_at == new_start and event.ends_at == new_start + timedelta(hours=1)
        kinds = set(Notification.objects.values_list("kind", flat=True))
        assert kinds == {"event_rescheduled", "event_sync"}
        assert services.update_event_from_discord(42, "?", "", new_start, None) is None  # inconnu

    def test_update_drops_deadline_now_after_start(self, mirrored):
        Event.objects.filter(pk=mirrored.pk).update(signup_deadline=mirrored.starts_at - timedelta(hours=1))
        snap = services.event_snapshot(mirrored.pk)
        earlier = snap.starts_at - timedelta(hours=5)
        event = services.update_event_from_discord(555, snap.name, snap.description, earlier, None)
        assert event.signup_deadline is None and event.starts_at == earlier

    def test_cancel_from_discord(self, mirrored):
        event = services.cancel_event_from_discord(555)
        assert event.status == "cancelled" and event.discord_event_id == ""
        assert set(Notification.objects.values_list("kind", flat=True)) == {"event_cancelled", "event_sync"}
        assert services.cancel_event_from_discord(555) is None  # identifiant effacé : rien à faire
        # Suppression d'un événement déjà passé : pas de message d'annulation.
        Event.objects.filter(pk=event.pk).update(
            status="planned", discord_event_id="556", starts_at=NOW - timedelta(days=1)
        )
        Notification.objects.all().delete()
        services.cancel_event_from_discord(556)
        assert list(Notification.objects.values_list("kind", flat=True)) == ["event_sync"]


class TestQuickSignup:
    def test_unknown_user_closed_event_and_leave(self, event, character, member):
        assert "compte" in services.quick_signup("nope", event.pk, "present")[0]
        assert services.quick_signup(member.discord_id, 10_000, "present")[0] == "Événement introuvable."
        assert services.quick_signup(member.discord_id, event.pk, "leave")[0] == "Tu n'étais pas inscrit."
        Signup.objects.create(event=event, user=member, character=character, role="heal")
        assert services.quick_signup(member.discord_id, event.pk, "leave")[0] == "Tu es désinscrit."
        assert not Signup.objects.exists()
        Event.objects.filter(pk=event.pk).update(status="cancelled")
        assert "closes" in services.quick_signup(member.discord_id, event.pk, "present")[0]

    def test_existing_signup_only_changes_status(self, event, character, member):
        Signup.objects.create(event=event, user=member, character=character, role="dps", comment="ok")
        message, choices = services.quick_signup(member.discord_id, event.pk, "late")
        assert choices is None and "mise à jour" in message
        signup = Signup.objects.get()
        assert (signup.role, signup.status, signup.comment) == ("dps", "late", "ok")

    def test_first_signup_asks_for_choice_then_signs_up(self, event, character, member):
        message, choices = services.quick_signup(member.discord_id, event.pk, "present")
        assert "quel personnage" in message
        assert [value for _, value in choices] == [f"{character.pk}:heal", f"{character.pk}:dps"]
        assert "Thrall (Chaman 60) — Heal" in choices[0][0]
        done = services.signup_with_choice(member.discord_id, event.pk, "present", choices[1][1])
        assert "Inscrit" in done and Signup.objects.get().role == "dps"
        assert (
            services.signup_with_choice(member.discord_id, event.pk, "present", "garbage")
            == "Choix invalide."
        )

    def test_single_possibility_signs_up_directly(self, event, member):
        Character.objects.create(
            owner=member,
            name="Jaina",
            player_class=PlayerClass.objects.get(slug="mage"),
            race=Race.objects.get(slug="human"),
            level=60,
            main_role="dps",
        )
        message, choices = services.quick_signup(member.discord_id, event.pk, "maybe")
        assert choices is None and "Inscrit" in message
        assert Signup.objects.get().status == "maybe"
        assert Notification.objects.filter(kind="event_sync", event=event).exists()

    def test_no_character_or_too_low_level(self, event, member):
        assert "personnage" in services.quick_signup(member.discord_id, event.pk, "present")[0]
        Character.objects.create(
            owner=member,
            name="Noob",
            player_class=PlayerClass.objects.get(slug="mage"),
            race=Race.objects.get(slug="human"),
            level=10,
            main_role="dps",
        )
        Event.objects.filter(pk=event.pk).update(min_level=20)
        assert "niveau 20" in services.quick_signup(member.discord_id, event.pk, "present")[0]


class TestPollSync:
    def test_snapshot_store_and_complete(self, officer):
        from apps.polls.models import Poll

        poll = Poll.objects.create(
            title="Nom de guilde",
            proposals_end=NOW + timedelta(days=1),
            votes_end=NOW + timedelta(days=2),
            created_by=officer,
        )
        snap = services.poll_snapshot(poll.pk)
        assert (
            snap.status == "proposals"
            and snap.discord_message_id == ""
            and "Nom de guilde" in snap.message_text
        )
        assert services.poll_snapshot(10_000) is None
        services.store_poll_message(poll.pk, "123", snap.status)
        poll.refresh_from_db()
        assert (poll.discord_message_id, poll.discord_synced_status) == ("123", "proposals")
        Notification.objects.create(kind="poll_sync", poll=poll, text="x")
        assert services.complete_poll_syncs(poll.pk) == 1
        assert services.channel_id_for("poll_sync") is None  # aucun salon configuré en test
