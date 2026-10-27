"""Flux de connexion Discord, avec l'API Discord simulée par respx."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client

from apps.accounts.auth_views import STATE_SESSION_KEY
from apps.accounts.models import DeactivationReason, SiteRole, User

API = settings.DISCORD_API_BASE
pytestmark = pytest.mark.django_db


def mock_discord(router: respx.MockRouter, *, user_id="12345", member_roles=("role-member",), member=True):
    router.post(f"{API}/oauth2/token").mock(return_value=httpx.Response(200, json={"access_token": "tok"}))
    router.get(f"{API}/users/@me").mock(
        return_value=httpx.Response(
            200, json={"id": user_id, "username": "koj", "global_name": "Koj", "avatar": "abc"}
        )
    )
    member_route = router.get(f"{API}/guilds/{settings.DISCORD_GUILD_ID}/members/{user_id}")
    if member:
        member_route.mock(return_value=httpx.Response(200, json={"roles": list(member_roles)}))
    else:
        member_route.mock(return_value=httpx.Response(404, json={"message": "Unknown Member"}))


def start_login(client: Client) -> str:
    """Lance le flux et renvoie le `state` posé en session."""
    response = client.get("/api/auth/discord/login/")
    assert response.status_code == 302
    location = urlparse(response["Location"])
    assert location.path == "/api/v10/oauth2/authorize"
    query = parse_qs(location.query)
    assert query["scope"] == ["identify"]
    assert query["redirect_uri"] == ["http://testserver/api/auth/discord/callback/"]
    state = query["state"][0]
    assert client.session[STATE_SESSION_KEY] == state
    return state


def callback(client: Client, state: str, code="the-code"):
    return client.get("/api/auth/discord/callback/", {"code": code, "state": state})


def error_code(response) -> str:
    assert response.status_code == 302
    location = urlparse(response["Location"])
    assert location.path == "/login"
    return parse_qs(location.query)["error"][0]


@respx.mock
def test_login_creates_user_and_opens_session(client):
    mock_discord(respx.mock)
    state = start_login(client)

    response = callback(client, state)

    assert response.status_code == 302
    assert response["Location"] == f"{settings.FRONTEND_URL}/"
    user = User.objects.get(discord_id="12345")
    assert user.display_name == "Koj"
    assert user.discord_avatar == "abc"
    assert user.site_role == SiteRole.MEMBER
    assert client.session["_auth_user_id"] == str(user.pk)
    assert STATE_SESSION_KEY not in client.session


@respx.mock
def test_first_gm_is_promoted_from_env(client):
    mock_discord(respx.mock, user_id=settings.DISCORD_FIRST_GM_ID)
    callback(client, start_login(client))
    assert User.objects.get(discord_id=settings.DISCORD_FIRST_GM_ID).site_role == SiteRole.GM


@respx.mock
def test_refuses_non_member(client):
    mock_discord(respx.mock, member=False)
    response = callback(client, start_login(client))
    assert error_code(response) == "not_member"
    assert not User.objects.exists()


@respx.mock
def test_refuses_member_without_allowed_role(client):
    mock_discord(respx.mock, member_roles=("role-visitor",))
    response = callback(client, start_login(client))
    assert error_code(response) == "missing_role"
    assert not User.objects.exists()


def test_refuses_bad_state(client):
    start_login(client)
    response = callback(client, "forged-state")
    assert error_code(response) == "state_mismatch"


def test_handles_user_denying_consent(client):
    start_login(client)
    response = client.get("/api/auth/discord/callback/", {"error": "access_denied"})
    assert error_code(response) == "discord_denied"


@respx.mock
def test_discord_outage_is_reported(client):
    respx.mock.post(f"{API}/oauth2/token").mock(return_value=httpx.Response(502))
    response = callback(client, start_login(client))
    assert error_code(response) == "discord_error"


@respx.mock
def test_manually_deactivated_user_is_refused(client):
    User.objects.create_user("12345", is_active=False, deactivation_reason=DeactivationReason.MANUAL)
    mock_discord(respx.mock)
    response = callback(client, start_login(client))
    assert error_code(response) == "deactivated"
    assert not User.objects.get(discord_id="12345").is_active


@respx.mock
def test_user_deactivated_by_discord_is_reactivated_when_role_is_back(client):
    User.objects.create_user("12345", is_active=False, deactivation_reason=DeactivationReason.DISCORD)
    mock_discord(respx.mock)
    response = callback(client, start_login(client))
    assert response["Location"] == f"{settings.FRONTEND_URL}/"
    user = User.objects.get(discord_id="12345")
    assert user.is_active
    assert user.deactivation_reason == ""


@respx.mock
def test_existing_user_keeps_custom_display_name(client):
    User.objects.create_user("12345", display_name="Mon surnom", site_role=SiteRole.OFFICER)
    mock_discord(respx.mock)
    callback(client, start_login(client))
    user = User.objects.get(discord_id="12345")
    assert user.display_name == "Mon surnom"
    assert user.discord_username == "Koj"
    assert user.site_role == SiteRole.OFFICER


@respx.mock
def test_logout_closes_session(client):
    mock_discord(respx.mock)
    callback(client, start_login(client))
    assert Session.objects.count() == 1

    response = client.post("/api/auth/logout/")

    assert response.status_code == 204
    assert "_auth_user_id" not in client.session
