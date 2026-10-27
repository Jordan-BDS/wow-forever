import pytest
from rest_framework.test import APIClient

from apps.accounts.models import SiteRole, User


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _make_user(discord_id: str, role: str, **extra) -> User:
    return User.objects.create_user(
        discord_id=discord_id,
        discord_username=f"user{discord_id}",
        display_name=extra.pop("display_name", f"User {discord_id}"),
        site_role=role,
        **extra,
    )


@pytest.fixture
def member(db) -> User:
    return _make_user("100", SiteRole.MEMBER)


@pytest.fixture
def other_member(db) -> User:
    return _make_user("101", SiteRole.MEMBER)


@pytest.fixture
def officer(db) -> User:
    return _make_user("200", SiteRole.OFFICER)


@pytest.fixture
def gm(db) -> User:
    return _make_user("300", SiteRole.GM)


@pytest.fixture
def as_user(api_client):
    def _login(user: User) -> APIClient:
        api_client.force_authenticate(user)
        return api_client

    return _login
