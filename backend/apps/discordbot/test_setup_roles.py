import httpx
import pytest
import respx
from django.conf import settings
from django.core.management import call_command

from apps.guild.models import GuildSettings

pytestmark = pytest.mark.django_db
API = settings.DISCORD_API_BASE
GUILD = settings.DISCORD_GUILD_ID


@respx.mock
def test_creates_missing_roles_assigns_members_and_saves_ids(capsys):
    respx.get(f"{API}/guilds/{GUILD}/roles").mock(
        return_value=httpx.Response(
            200, json=[{"id": "1", "name": "@everyone"}, {"id": "50", "name": "membre"}]
        )
    )
    created = respx.post(f"{API}/guilds/{GUILD}/roles").mock(
        return_value=httpx.Response(200, json={"id": "60", "name": "Officier"})
    )
    respx.get(f"{API}/guilds/{GUILD}/members").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"user": {"id": "u1", "username": "koj"}, "roles": []},
                {"user": {"id": "u2", "username": "deja", "global_name": "Déjà"}, "roles": ["50"]},
                {"user": {"id": "b1", "username": "bot", "bot": True}, "roles": []},
            ],
        )
    )
    assigned = respx.put(f"{API}/guilds/{GUILD}/members/u1/roles/50").mock(return_value=httpx.Response(204))

    call_command("discord_setup_roles")

    assert (
        created.call_count == 1
        and created.calls[0].request.content
        and b"Officier" in created.calls[0].request.content
    )
    assert assigned.call_count == 1  # u2 l'a déjà, le bot est ignoré
    stored = GuildSettings.load()
    assert stored.discord_allowed_role_ids == "50,60" and stored.discord_guild_id == GUILD
    out = capsys.readouterr().out
    assert "déjà présent" in out and "Officier » créé" in out and "1 sans le rôle Membre" in out


@respx.mock
def test_dry_run_changes_nothing(capsys):
    respx.get(f"{API}/guilds/{GUILD}/roles").mock(return_value=httpx.Response(200, json=[]))
    post = respx.post(f"{API}/guilds/{GUILD}/roles")
    respx.get(f"{API}/guilds/{GUILD}/members").mock(
        return_value=httpx.Response(200, json=[{"user": {"id": "u1", "username": "koj"}, "roles": []}])
    )
    call_command("discord_setup_roles", "--dry-run")
    assert post.call_count == 0
    assert GuildSettings.load().discord_allowed_role_ids == ""
    assert "[dry-run]" in capsys.readouterr().out


@respx.mock
def test_explains_missing_members_intent():
    respx.get(f"{API}/guilds/{GUILD}/roles").mock(return_value=httpx.Response(200, json=[]))
    respx.post(f"{API}/guilds/{GUILD}/roles").mock(
        side_effect=lambda r: httpx.Response(200, json={"id": "9", "name": "x"})
    )
    respx.get(f"{API}/guilds/{GUILD}/members").mock(
        return_value=httpx.Response(403, json={"message": "Missing Access"})
    )
    with pytest.raises(Exception, match="Server Members"):
        call_command("discord_setup_roles")
