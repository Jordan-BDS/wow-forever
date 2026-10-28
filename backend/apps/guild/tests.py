import pytest

from apps.guild.models import GuildSettings

pytestmark = pytest.mark.django_db


def test_settings_are_created_on_first_read(as_user, member):
    response = as_user(member).get("/api/guild/")
    assert response.status_code == 200
    assert response.data["name"] == ""
    assert GuildSettings.objects.count() == 1


def test_only_gm_can_update(as_user, member, officer, gm):
    payload = {"name": "Les Potes", "faction": "horde", "realm": "Auberdine"}
    assert as_user(member).patch("/api/guild/", payload, format="json").status_code == 403
    assert as_user(officer).patch("/api/guild/", payload, format="json").status_code == 403

    response = as_user(gm).patch("/api/guild/", payload, format="json")

    assert response.status_code == 200
    settings = GuildSettings.load()
    assert (settings.name, settings.faction, settings.realm) == ("Les Potes", "horde", "Auberdine")


def test_values_are_public_and_trimmed(as_user, member, gm):
    response = as_user(gm).patch(
        "/api/guild/", {"values": "  Entraide.\r\n\r\nBonne humeur.  "}, format="json"
    )
    assert response.status_code == 200
    assert response.data["values"] == "Entraide.\n\nBonne humeur."
    assert as_user(member).get("/api/guild/").data["values"] == "Entraide.\n\nBonne humeur."


def test_rejects_unknown_faction(as_user, gm):
    response = as_user(gm).patch("/api/guild/", {"faction": "scourge"}, format="json")
    assert response.status_code == 400


def test_singleton_never_duplicates(db):
    GuildSettings(name="A").save()
    GuildSettings(name="B").save()
    assert GuildSettings.objects.count() == 1
    assert GuildSettings.load().name == "B"


class TestDiscordSettings:
    def test_site_values_override_environment_and_secrets_are_hidden(self, as_user, gm, member):
        client = as_user(gm)
        before = client.get("/api/guild/").data
        assert before["discord_client_id"] == "client-id"  # valeur d'environnement de test
        assert before["discord_bot_token_set"] is True and "discord_bot_token" not in before
        response = client.patch(
            "/api/guild/",
            {"discord_client_id": "111", "discord_guild_id": "222", "discord_allowed_role_ids": "333, 444",
             "discord_first_gm_id": "555", "discord_bot_token": "new-token", "discord_client_secret": ""},
            format="json",
        )  # fmt: skip
        assert response.status_code == 200, response.data
        assert response.data["discord_allowed_role_ids"] == "333, 444"
        from apps.guild.config import discord_config

        config = discord_config()
        assert (config.client_id, config.guild_id, config.allowed_role_ids, config.first_gm_id) == (
            "111",
            "222",
            ["333", "444"],
            "555",
        )
        assert config.bot_token == "new-token" and config.client_secret == "client-secret"  # vide = inchangé
        assert "discord_client_id" not in as_user(member).get("/api/guild/").data

    def test_rejects_non_numeric_ids(self, as_user, gm):
        response = as_user(gm).patch("/api/guild/", {"discord_allowed_role_ids": "abc"}, format="json")
        assert response.status_code == 400

    def test_login_refused_when_not_configured(self, client, settings):
        settings.DISCORD_CLIENT_ID = ""
        response = client.get("/api/auth/discord/login/")
        assert response.status_code == 302 and "error=not_configured" in response["Location"]

    def test_discord_check_lists_roles(self, as_user, gm):
        import httpx
        import respx
        from django.conf import settings as dj

        with respx.mock:
            respx.get(f"{dj.DISCORD_API_BASE}/guilds/999").mock(
                return_value=httpx.Response(200, json={"name": "Les Zouaves"})
            )
            respx.get(f"{dj.DISCORD_API_BASE}/guilds/999/roles").mock(return_value=httpx.Response(200, json=[
                {"id": "role-member", "name": "Membre", "position": 2},
                {"id": "x", "name": "@everyone", "position": 0},
                {"id": "role-visitor", "name": "Visiteur", "position": 1},
            ]))  # fmt: skip
            respx.get(f"{dj.DISCORD_API_BASE}/guilds/999/channels").mock(
                return_value=httpx.Response(200, json=[])
            )
            response = as_user(gm).post("/api/guild/discord-check/")
        assert response.status_code == 200, response.data
        assert response.data["guild_name"] == "Les Zouaves"
        assert [(r["name"], r["allowed"]) for r in response.data["roles"]] == [
            ("Membre", True),
            ("Visiteur", False),
        ]
        assert "role-officer" in response.data["detail"]  # autorisé dans l'env de test mais absent du serveur
        assert response.data["ok"] is False


class TestDiscordChannels:
    def test_channel_settings_saved_and_validated(self, as_user, gm):
        client = as_user(gm)
        response = client.patch(
            "/api/guild/",
            {
                "discord_agenda_channel_id": "11",
                "discord_crafts_channel_id": "22",
                "discord_polls_channel_id": "33",
            },
            format="json",
        )
        assert response.status_code == 200, response.data
        stored = GuildSettings.load()
        assert (
            stored.discord_agenda_channel_id,
            stored.discord_crafts_channel_id,
            stored.discord_polls_channel_id,
        ) == (
            "11",
            "22",
            "33",
        )
        assert (
            client.patch("/api/guild/", {"discord_agenda_channel_id": "abc"}, format="json").status_code
            == 400
        )

    def test_discord_check_lists_text_channels_in_discord_order(self, as_user, gm):
        import httpx
        import respx
        from django.conf import settings as dj

        with respx.mock:
            respx.get(f"{dj.DISCORD_API_BASE}/guilds/999").mock(
                return_value=httpx.Response(200, json={"name": "G"})
            )
            respx.get(f"{dj.DISCORD_API_BASE}/guilds/999/roles").mock(
                return_value=httpx.Response(200, json=[])
            )
            respx.get(f"{dj.DISCORD_API_BASE}/guilds/999/channels").mock(return_value=httpx.Response(200, json=[  # noqa: E501
                {"id": "cat-b", "name": "Vocal", "type": 4, "position": 2},
                {"id": "cat-a", "name": "Textuels", "type": 4, "position": 1},
                {"id": "c-voice", "name": "Général", "type": 2, "position": 0, "parent_id": "cat-b"},
                {"id": "c-2", "name": "agenda", "type": 0, "position": 1, "parent_id": "cat-a"},
                {"id": "c-1", "name": "général", "type": 0, "position": 0, "parent_id": "cat-a"},
                {"id": "c-0", "name": "sans-categorie", "type": 0, "position": 5},
            ]))  # fmt: skip
            response = as_user(gm).post("/api/guild/discord-check/")
        assert [(c["name"], c["category"]) for c in response.data["channels"]] == [
            ("sans-categorie", ""),
            ("général", "Textuels"),
            ("agenda", "Textuels"),
        ]


class TestSetupChannelsCommand:
    def _run(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("discord_setup_channels", *args, stdout=out)
        return out.getvalue()

    def test_creates_missing_channels_read_only_and_saves_ids(self, db):
        import json

        import httpx
        import respx
        from django.conf import settings as dj

        from apps.discordbot.management.commands import discord_setup_channels as cmd

        created = []

        def create(request):
            payload = json.loads(request.content)
            created.append(payload)
            return httpx.Response(201, json={"id": f"new-{len(created)}", "name": payload["name"]})

        with respx.mock:
            respx.get(f"{dj.DISCORD_API_BASE}/users/@me").mock(
                return_value=httpx.Response(200, json={"id": "bot"})
            )
            respx.get(f"{dj.DISCORD_API_BASE}/guilds/999/channels").mock(return_value=httpx.Response(200, json=[  # noqa: E501
                {"id": "cat", "name": "Salons textuels", "type": 4, "position": 0},
                {"id": "g", "name": "général", "type": 0, "position": 0, "parent_id": "cat"},
                {"id": "p", "name": "sondages", "type": 0, "position": 1, "parent_id": "cat"},
            ]))  # fmt: skip
            respx.post(f"{dj.DISCORD_API_BASE}/guilds/999/channels").mock(side_effect=create)
            output = self._run()

        assert [c["name"] for c in created] == ["agenda", "demande-de-craft"]
        assert all(c["parent_id"] == "cat" and c["type"] == 0 for c in created)
        everyone, bot = created[0]["permission_overwrites"]
        assert everyone["id"] == "999" and int(everyone["deny"]) & cmd.SEND_MESSAGES
        assert int(everyone["allow"]) & cmd.ADD_REACTIONS and int(everyone["allow"]) & cmd.VIEW_CHANNEL
        assert (
            bot["id"] == "bot"
            and int(bot["allow"]) & cmd.PIN_MESSAGES
            and int(bot["allow"]) & cmd.SEND_MESSAGES
        )
        stored = GuildSettings.load()
        assert (
            stored.discord_agenda_channel_id,
            stored.discord_crafts_channel_id,
            stored.discord_polls_channel_id,
        ) == (
            "new-1",
            "new-2",
            "p",
        )
        assert "créé" in output and "sondages" in output

    def test_existing_channels_get_permissions_fixed_and_dry_run_changes_nothing(self, db):
        import httpx
        import respx
        from django.conf import settings as dj

        from apps.discordbot.management.commands import discord_setup_channels as cmd

        channels = [
            {"id": "a", "name": "agenda", "type": 0, "position": 0, "permission_overwrites": []},
            {"id": "c", "name": "demande-de-craft", "type": 0, "position": 1,
             "permission_overwrites": cmd.overwrites("999", "bot")},
        ]  # fmt: skip
        with respx.mock:
            respx.get(f"{dj.DISCORD_API_BASE}/users/@me").mock(
                return_value=httpx.Response(200, json={"id": "bot"})
            )
            respx.get(f"{dj.DISCORD_API_BASE}/guilds/999/channels").mock(
                return_value=httpx.Response(200, json=channels)
            )
            patched = respx.patch(f"{dj.DISCORD_API_BASE}/channels/a").mock(
                return_value=httpx.Response(200, json={})
            )
            untouched = respx.patch(f"{dj.DISCORD_API_BASE}/channels/c").mock(
                return_value=httpx.Response(200, json={})
            )
            output = self._run()
            assert patched.called and not untouched.called
            assert GuildSettings.load().discord_agenda_channel_id == "a"
            assert "Pas de salon « #sondages »" in output

            GuildSettings.objects.all().delete()
            output = self._run("--dry-run")
            assert GuildSettings.load().discord_agenda_channel_id == ""
