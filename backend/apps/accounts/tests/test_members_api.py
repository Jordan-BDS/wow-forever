import pytest
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session

from apps.accounts.models import DeactivationReason, SiteRole, User
from apps.accounts.services import delete_user_sessions

pytestmark = pytest.mark.django_db


def test_me_requires_login(api_client):
    assert api_client.get("/api/auth/me/").status_code == 403


def test_me_returns_profile_and_sets_csrf_cookie(as_user, member):
    response = as_user(member).get("/api/auth/me/")
    assert response.status_code == 200
    assert response.data["discord_id"] == "100"
    assert response.data["site_role"] == "member"
    assert response.data["avatar_url"].startswith("https://cdn.discordapp.com/")
    assert "csrftoken" in response.cookies


def test_me_can_update_display_name_and_bio_only(as_user, member):
    response = as_user(member).patch(
        "/api/auth/me/", {"display_name": "Nouveau", "bio": "Salut", "site_role": "gm"}, format="json"
    )
    assert response.status_code == 200
    member.refresh_from_db()
    assert member.display_name == "Nouveau"
    assert member.bio == "Salut"
    assert member.site_role == SiteRole.MEMBER


def test_members_list_visible_to_everyone(as_user, member, officer, gm):
    response = as_user(member).get("/api/members/")
    assert response.status_code == 200
    assert {m["discord_id"] for m in response.data} == {"100", "200", "300"}


class TestRoleChange:
    def test_gm_can_promote_to_officer(self, as_user, gm, member):
        response = as_user(gm).post(
            f"/api/members/{member.pk}/role/", {"site_role": "officer"}, format="json"
        )
        assert response.status_code == 200
        member.refresh_from_db()
        assert member.site_role == SiteRole.OFFICER

    def test_officer_cannot_change_roles(self, as_user, officer, member):
        response = as_user(officer).post(
            f"/api/members/{member.pk}/role/", {"site_role": "officer"}, format="json"
        )
        assert response.status_code == 403

    def test_gm_cannot_change_own_role(self, as_user, gm):
        response = as_user(gm).post(f"/api/members/{gm.pk}/role/", {"site_role": "member"}, format="json")
        assert response.status_code == 403
        gm.refresh_from_db()
        assert gm.site_role == SiteRole.GM

    def test_rejects_unknown_role(self, as_user, gm, member):
        response = as_user(gm).post(f"/api/members/{member.pk}/role/", {"site_role": "king"}, format="json")
        assert response.status_code == 400


class TestDeactivation:
    def test_officer_can_deactivate_member_and_kill_sessions(self, as_user, officer, member):
        store = SessionStore()
        store[SESSION_KEY] = str(member.pk)
        store.create()
        assert Session.objects.count() == 1

        response = as_user(officer).post(f"/api/members/{member.pk}/deactivate/")

        assert response.status_code == 200
        member.refresh_from_db()
        assert not member.is_active
        assert member.deactivation_reason == DeactivationReason.MANUAL
        assert Session.objects.count() == 0

    def test_officer_cannot_deactivate_officer_or_gm(self, as_user, officer, gm):
        other_officer = User.objects.create_user("201", site_role=SiteRole.OFFICER)
        assert as_user(officer).post(f"/api/members/{other_officer.pk}/deactivate/").status_code == 403
        assert as_user(officer).post(f"/api/members/{gm.pk}/deactivate/").status_code == 403

    def test_member_cannot_deactivate(self, as_user, member, other_member):
        assert as_user(member).post(f"/api/members/{other_member.pk}/deactivate/").status_code == 403

    def test_cannot_deactivate_self(self, as_user, gm):
        assert as_user(gm).post(f"/api/members/{gm.pk}/deactivate/").status_code == 403

    def test_reactivate(self, as_user, gm, member):
        member.is_active = False
        member.deactivation_reason = DeactivationReason.MANUAL
        member.save()
        response = as_user(gm).post(f"/api/members/{member.pk}/reactivate/")
        assert response.status_code == 200
        member.refresh_from_db()
        assert member.is_active
        assert member.deactivation_reason == ""


def test_delete_user_sessions_only_touches_that_user(member, other_member):
    for user in (member, other_member):
        store = SessionStore()
        store[SESSION_KEY] = str(user.pk)
        store.create()
    assert delete_user_sessions(member) == 1
    assert Session.objects.count() == 1


def test_me_can_update_dm_preferences(as_user, member):
    client = as_user(member)
    response = client.patch(
        "/api/auth/me/", {"dm_enabled": False, "dm_muted_kinds": ["placement"]}, format="json"
    )
    assert response.status_code == 200, response.data
    assert response.data["dm_enabled"] is False and response.data["dm_muted_kinds"] == ["placement"]
    assert client.patch("/api/auth/me/", {"dm_muted_kinds": ["spam"]}, format="json").status_code == 400
