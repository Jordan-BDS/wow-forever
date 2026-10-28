from datetime import timedelta

import pytest
from django.utils import timezone

from apps.characters.models import Character
from apps.events.models import Event, Signup
from apps.gamedata.models import Instance, PlayerClass, Race
from apps.gamedata.seed import seed

pytestmark = pytest.mark.django_db

NOW = timezone.now()
TOMORROW = NOW + timedelta(days=1)


@pytest.fixture(autouse=True)
def gamedata(db):
    seed()


def make_character(
    owner, name, class_slug="warrior", race_slug="orc", level=60, main_role="tank", off_role="dps"
):
    return Character.objects.create(
        owner=owner,
        name=name,
        player_class=PlayerClass.objects.get(slug=class_slug),
        race=Race.objects.get(slug=race_slug),
        level=level,
        main_role=main_role,
        off_role=off_role,
        is_main=True,
    )


def event_payload(**overrides):
    base = {
        "title": "Cœur du Magma",
        "kind": "raid",
        "instance": "molten-core",
        "starts_at": TOMORROW.isoformat(),
        "ends_at": (TOMORROW + timedelta(hours=3)).isoformat(),
        "max_size": 40,
        "need_tanks": 4,
        "need_heals": 10,
        "need_dps": 26,
        "min_level": 58,
        "signup_deadline": (TOMORROW - timedelta(hours=2)).isoformat(),
    }
    return {**base, **overrides}


def create_event(client, **overrides):
    return client.post("/api/events/", event_payload(**overrides), format="json")


class TestEvents:
    def test_member_creates_event_and_is_organizer(self, as_user, member):
        response = create_event(as_user(member))
        assert response.status_code == 201, response.data
        assert response.data["organizer"]["id"] == member.pk
        assert response.data["effective_status"] == "planned"
        assert response.data["signups_open"] is True
        assert response.data["candidates"] == {"tank": 0, "heal": 0, "dps": 0}

    def test_instance_must_match_kind(self, as_user, member):
        response = create_event(as_user(member), kind="dungeon", instance="molten-core")
        assert response.status_code == 400
        assert "instance" in response.data
        response = create_event(as_user(member), kind="social", instance=None)
        assert response.status_code == 201

    def test_date_consistency(self, as_user, member):
        assert create_event(as_user(member), ends_at=NOW.isoformat()).status_code == 400
        assert (
            create_event(
                as_user(member), signup_deadline=(TOMORROW + timedelta(hours=1)).isoformat()
            ).status_code
            == 400
        )

    def test_only_organizer_or_officer_edits(self, as_user, member, other_member, officer):
        event_id = create_event(as_user(member)).data["id"]
        assert (
            as_user(other_member).patch(f"/api/events/{event_id}/", {"title": "x"}, format="json").status_code
            == 403
        )
        assert (
            as_user(member).patch(f"/api/events/{event_id}/", {"title": "Mien"}, format="json").status_code
            == 200
        )
        assert (
            as_user(officer)
            .patch(f"/api/events/{event_id}/", {"title": "Officier"}, format="json")
            .status_code
            == 200
        )

    def test_only_organizer_or_officer_deletes(self, as_user, member, other_member, officer):
        from apps.events.models import Event

        event_id = create_event(as_user(member)).data["id"]
        assert as_user(other_member).delete(f"/api/events/{event_id}/").status_code == 403
        assert as_user(member).delete(f"/api/events/{event_id}/").status_code == 204
        assert not Event.objects.filter(pk=event_id).exists()
        event_id = create_event(as_user(member)).data["id"]
        assert as_user(officer).delete(f"/api/events/{event_id}/").status_code == 204

    def test_cancel_and_restore(self, as_user, member):
        client = as_user(member)
        event_id = create_event(client).data["id"]
        cancelled = client.post(f"/api/events/{event_id}/cancel/")
        assert cancelled.data["effective_status"] == "cancelled"
        assert cancelled.data["signups_open"] is False
        assert client.post(f"/api/events/{event_id}/restore/").data["effective_status"] == "planned"

    def test_past_event_is_done(self, as_user, member):
        event = Event.objects.create(
            title="Hier", kind="social", starts_at=NOW - timedelta(days=1), organizer=member
        )
        response = as_user(member).get(f"/api/events/{event.pk}/")
        assert response.data["effective_status"] == "done"
        assert response.data["signups_open"] is False

    def test_list_defaults_to_upcoming_and_accepts_window(self, as_user, member):
        Event.objects.create(
            title="Vieux", kind="social", starts_at=NOW - timedelta(days=10), organizer=member
        )
        Event.objects.create(title="Bientôt", kind="social", starts_at=TOMORROW, organizer=member)
        Event.objects.create(
            title="Loin", kind="social", starts_at=NOW + timedelta(days=40), organizer=member
        )
        client = as_user(member)
        assert [e["title"] for e in client.get("/api/events/").data] == ["Bientôt", "Loin"]
        window = client.get(
            "/api/events/",
            {"from": (NOW - timedelta(days=30)).isoformat(), "to": (NOW + timedelta(days=30)).isoformat()},
        )
        assert [e["title"] for e in window.data] == ["Vieux", "Bientôt"]

    def test_duplicate_shifts_dates_and_drops_signups(self, as_user, member, other_member):
        client = as_user(member)
        event_id = create_event(client).data["id"]
        make_character(other_member, "Grom")
        as_user(other_member).post(
            f"/api/events/{event_id}/signup/",
            {"character": Character.objects.get(name="Grom").pk, "role": "tank"},
            format="json",
        )
        new_start = TOMORROW + timedelta(days=7)
        response = as_user(other_member).post(
            f"/api/events/{event_id}/duplicate/", {"starts_at": new_start.isoformat()}, format="json"
        )
        assert response.status_code == 201, response.data
        copy = Event.objects.get(pk=response.data["id"])
        assert copy.organizer == other_member
        assert copy.starts_at == new_start
        assert copy.ends_at == new_start + timedelta(hours=3)
        assert copy.signup_deadline == new_start - timedelta(hours=2)
        assert copy.signups.count() == 0
        assert copy.need_tanks == 4


class TestSignups:
    @pytest.fixture
    def event_id(self, as_user, officer):
        return create_event(as_user(officer)).data["id"]

    def test_signup_with_own_character_and_role(self, as_user, member, event_id):
        character = make_character(member, "Thrall", "shaman", "orc", main_role="heal", off_role="dps")
        response = as_user(member).post(
            f"/api/events/{event_id}/signup/",
            {"character": character.pk, "role": "heal", "status": "present", "comment": "Potions ok"},
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["character"]["player_class"] == "shaman"
        assert response.data["placement"] == "confirmed"  # confirmé d'office : il reste de la place en heal
        event = as_user(member).get(f"/api/events/{event_id}/").data
        assert event["my_signup"]["id"] == response.data["id"]
        assert event["candidates"] == {"tank": 0, "heal": 1, "dps": 0}

    def test_signup_is_upserted_not_duplicated(self, as_user, member, event_id):
        character = make_character(member, "Thrall")
        client = as_user(member)
        first = client.post(
            f"/api/events/{event_id}/signup/", {"character": character.pk, "role": "tank"}, format="json"
        )
        second = client.post(
            f"/api/events/{event_id}/signup/",
            {"character": character.pk, "role": "dps", "status": "maybe"},
            format="json",
        )
        assert (first.status_code, second.status_code) == (201, 200)
        assert Signup.objects.filter(event_id=event_id, user=member).count() == 1
        assert second.data["role"] == "dps"

    def test_rejects_wrong_role_other_owner_and_low_level(self, as_user, member, other_member, event_id):
        mage = make_character(member, "Jaina", "mage", "undead", main_role="dps", off_role="")
        low = make_character(other_member, "Petit", level=20)
        client = as_user(member)
        assert (
            client.post(
                f"/api/events/{event_id}/signup/", {"character": mage.pk, "role": "heal"}, format="json"
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/events/{event_id}/signup/", {"character": low.pk, "role": "tank"}, format="json"
            ).status_code
            == 400
        )
        assert (
            as_user(other_member)
            .post(f"/api/events/{event_id}/signup/", {"character": low.pk, "role": "tank"}, format="json")
            .status_code
            == 400
        )

    def test_unsign(self, as_user, member, event_id):
        character = make_character(member, "Thrall")
        client = as_user(member)
        client.post(
            f"/api/events/{event_id}/signup/", {"character": character.pk, "role": "tank"}, format="json"
        )
        assert client.delete(f"/api/events/{event_id}/signup/").status_code == 204
        assert client.delete(f"/api/events/{event_id}/signup/").status_code == 404

    def test_closed_signups_block_members_but_not_organizer(self, as_user, member, officer, event_id):
        event = Event.objects.get(pk=event_id)
        event.signup_deadline = NOW - timedelta(minutes=5)
        event.save()
        character = make_character(member, "Thrall")
        denied = as_user(member).post(
            f"/api/events/{event_id}/signup/", {"character": character.pk, "role": "tank"}, format="json"
        )
        assert denied.status_code == 400
        forced = as_user(officer).post(
            f"/api/events/{event_id}/signup/?user={member.pk}",
            {"character": character.pk, "role": "tank"},
            format="json",
        )
        assert forced.status_code == 201, forced.data
        assert forced.data["user"]["id"] == member.pk

    def test_member_cannot_sign_up_someone_else(self, as_user, member, other_member, event_id):
        character = make_character(other_member, "Grom")
        response = as_user(member).post(
            f"/api/events/{event_id}/signup/?user={other_member.pk}",
            {"character": character.pk, "role": "tank"},
            format="json",
        )
        assert response.status_code == 403

    def test_organizer_places_candidates(self, as_user, member, officer, event_id):
        character = make_character(member, "Thrall")
        signup_id = (
            as_user(member)
            .post(
                f"/api/events/{event_id}/signup/", {"character": character.pk, "role": "tank"}, format="json"
            )
            .data["id"]
        )
        denied = as_user(member).patch(
            f"/api/signups/{signup_id}/", {"placement": "confirmed"}, format="json"
        )
        assert denied.status_code == 403
        placed = as_user(officer).patch(
            f"/api/signups/{signup_id}/", {"placement": "confirmed"}, format="json"
        )
        assert placed.status_code == 200, placed.data
        assert placed.data["placement"] == "confirmed"
        event = as_user(member).get(f"/api/events/{event_id}/").data
        assert event["confirmed"] == {"tank": 1, "heal": 0, "dps": 0}
        benched = as_user(officer).patch(f"/api/signups/{signup_id}/", {"placement": "bench"}, format="json")
        assert benched.data["placement"] == "bench"

    def test_organizer_removes_signup(self, as_user, member, officer, event_id):
        character = make_character(member, "Thrall")
        signup_id = (
            as_user(member)
            .post(
                f"/api/events/{event_id}/signup/", {"character": character.pk, "role": "tank"}, format="json"
            )
            .data["id"]
        )
        assert as_user(officer).delete(f"/api/signups/{signup_id}/").status_code == 204
        assert not Signup.objects.filter(pk=signup_id).exists()

    def test_absent_signups_are_not_candidates(self, as_user, member, event_id):
        character = make_character(member, "Thrall")
        as_user(member).post(
            f"/api/events/{event_id}/signup/",
            {"character": character.pk, "role": "tank", "status": "absent"},
            format="json",
        )
        event = as_user(member).get(f"/api/events/{event_id}/").data
        assert event["candidates"] == {"tank": 0, "heal": 0, "dps": 0}
        assert len(event["signups"]) == 1


def test_instance_default_needs_available(db):
    assert Instance.objects.get(slug="deadmines").default_dps == 3


class TestNotificationHooks:
    def test_create_cancel_reschedule_announce_enqueue_channel_messages(self, as_user, officer):
        from apps.notifications.models import Notification

        client = as_user(officer)
        event_id = create_event(client).data["id"]
        # La création ne poste plus de texte : le message d'inscription synchronisé fait office d'annonce.
        assert list(Notification.objects.values_list("kind", flat=True)) == ["event_sync"]
        client.patch(f"/api/events/{event_id}/", {"title": "Renommé"}, format="json")
        assert Notification.objects.count() == 1  # un renommage ne fait que resynchroniser (déjà en attente)
        client.patch(
            f"/api/events/{event_id}/",
            {"starts_at": (TOMORROW + timedelta(hours=1)).isoformat(), "signup_deadline": None},
            format="json",
        )
        assert Notification.objects.latest("pk").kind == "event_rescheduled"
        client.post(f"/api/events/{event_id}/announce/")
        assert Notification.objects.latest("pk").kind == "composition"
        client.post(f"/api/events/{event_id}/cancel/")
        client.post(f"/api/events/{event_id}/cancel/")  # idempotent
        assert list(Notification.objects.filter(kind="event_cancelled")).__len__() == 1
        assert Notification.objects.filter(kind="event_sync").count() == 1  # toujours dédupliquée

    def test_signups_and_placements_request_a_discord_sync(self, as_user, member, officer):
        from apps.notifications.models import Notification

        event_id = create_event(as_user(officer)).data["id"]
        Notification.objects.update(status="sent")  # le bot a traité la création
        character = make_character(member, "Thrall")
        response = as_user(member).post(
            f"/api/events/{event_id}/signup/", {"character": character.pk, "role": "tank"}, format="json"
        )
        assert response.status_code == 201
        assert Notification.objects.filter(kind="event_sync", status="pending").count() == 1
        Notification.objects.update(status="sent")
        as_user(officer).patch(
            f"/api/signups/{response.data['id']}/", {"placement": "confirmed"}, format="json"
        )
        assert Notification.objects.filter(kind="event_sync", status="pending").count() == 1
        Notification.objects.update(status="sent")
        assert as_user(member).delete(f"/api/events/{event_id}/signup/").status_code == 204
        assert Notification.objects.filter(kind="event_sync", status="pending").count() == 1
        assert as_user(member).delete(f"/api/events/{event_id}/signup/").status_code == 404

    def test_discord_url_exposed_when_mirrored(self, as_user, officer, settings):
        settings.DISCORD_GUILD_ID = "4242"
        event_id = create_event(as_user(officer)).data["id"]
        assert as_user(officer).get(f"/api/events/{event_id}/").data["discord_url"] is None
        Event.objects.filter(pk=event_id).update(discord_event_id="777")
        url = as_user(officer).get(f"/api/events/{event_id}/").data["discord_url"]
        assert url == "https://discord.com/events/4242/777"

    def test_placement_change_sends_dm(self, as_user, member, officer):
        from apps.notifications.models import Notification

        event_id = create_event(as_user(officer)).data["id"]
        character = make_character(member, "Thrall")
        signup_id = (
            as_user(member)
            .post(
                f"/api/events/{event_id}/signup/", {"character": character.pk, "role": "tank"}, format="json"
            )
            .data["id"]
        )
        # Confirmé d'office à l'inscription (sans MP) ; l'organisateur le met sur le banc puis le reconfirme.
        assert not Notification.objects.filter(kind="placement").exists()
        as_user(officer).patch(f"/api/signups/{signup_id}/", {"placement": "bench"}, format="json")
        dm = Notification.objects.get(kind="placement")
        assert dm.recipient == member and "banc" in dm.text
        as_user(officer).patch(f"/api/signups/{signup_id}/", {"placement": "confirmed"}, format="json")
        assert "confirmé" in Notification.objects.filter(kind="placement").latest("pk").text
        as_user(officer).patch(f"/api/signups/{signup_id}/", {"placement": "confirmed"}, format="json")
        assert Notification.objects.filter(kind="placement").count() == 2


class TestAutoPlacement:
    """Un « Présent » est confirmé d'office tant qu'il reste de la place (besoin du rôle, puis taille max)."""

    def _signup(self, as_user, user, event_id, character, role="tank", status="present"):
        response = as_user(user).post(
            f"/api/events/{event_id}/signup/",
            {"character": character.pk, "role": role, "status": status},
            format="json",
        )
        assert response.status_code in (200, 201), response.data
        return response.data

    def test_present_is_confirmed_while_role_has_room(self, as_user, member, other_member, officer):
        event_id = create_event(as_user(officer), need_tanks=1, max_size=5).data["id"]
        thrall = make_character(member, "Thrall")
        garrosh = make_character(other_member, "Garrosh")
        assert self._signup(as_user, member, event_id, thrall)["placement"] == "confirmed"
        # Le besoin en tanks (1) est atteint : le second reste non placé, l'organisateur arbitre.
        assert self._signup(as_user, other_member, event_id, garrosh)["placement"] == "unplaced"
        # En DPS (3 attendus, 0 confirmé), il est confirmé.
        assert self._signup(as_user, other_member, event_id, garrosh, role="dps")["placement"] == "confirmed"

    def test_max_size_caps_when_no_role_need(self, as_user, member, other_member, officer):
        payload = dict(need_tanks=None, need_heals=None, need_dps=None, max_size=1)
        event_id = create_event(as_user(officer), **payload).data["id"]
        assert (
            self._signup(as_user, member, event_id, make_character(member, "Thrall"))["placement"]
            == "confirmed"
        )
        garrosh = make_character(other_member, "Garrosh")
        assert self._signup(as_user, other_member, event_id, garrosh)["placement"] == "unplaced"

    def test_no_limits_means_everyone_confirmed(self, as_user, member, officer):
        payload = dict(need_tanks=None, need_heals=None, need_dps=None, max_size=None)
        event_id = create_event(as_user(officer), **payload).data["id"]
        assert (
            self._signup(as_user, member, event_id, make_character(member, "Thrall"))["placement"]
            == "confirmed"
        )

    def test_maybe_stays_unplaced_and_absent_frees_the_slot(self, as_user, member, other_member, officer):
        event_id = create_event(as_user(officer), need_tanks=1).data["id"]
        thrall = make_character(member, "Thrall")
        garrosh = make_character(other_member, "Garrosh")
        assert self._signup(as_user, member, event_id, thrall, status="maybe")["placement"] == "unplaced"
        assert self._signup(as_user, member, event_id, thrall)["placement"] == "confirmed"
        assert self._signup(as_user, other_member, event_id, garrosh)["placement"] == "unplaced"
        assert self._signup(as_user, member, event_id, thrall, status="absent")["placement"] == "unplaced"
        # La place libérée profite au suivant qui (re)confirme sa présence.
        assert self._signup(as_user, other_member, event_id, garrosh)["placement"] == "confirmed"
        # Pas de MP « confirmé » pour une confirmation automatique : c'est l'action du joueur lui-même.
        from apps.notifications.models import Notification

        assert not Notification.objects.filter(kind="placement").exists()

    def test_bench_decided_by_organizer_is_kept(self, as_user, member, officer):
        event_id = create_event(as_user(officer), need_tanks=4).data["id"]
        thrall = make_character(member, "Thrall")
        signup_id = self._signup(as_user, member, event_id, thrall)["id"]
        as_user(officer).patch(f"/api/signups/{signup_id}/", {"placement": "bench"}, format="json")
        assert self._signup(as_user, member, event_id, thrall, status="late")["placement"] == "bench"
        assert self._signup(as_user, member, event_id, thrall)["placement"] == "bench"
