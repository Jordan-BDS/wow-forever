"""Client Battle.net (jeton, espaces de noms Forever, 404, nouvelles tentatives) et archive brute."""

import io
import json

import httpx
import pytest
from django.core.management import call_command

from apps.characters.models import Character
from apps.gamedata.models import PlayerClass, Race
from apps.gamedata.seed import seed
from apps.guild.models import GuildSettings

from . import services
from .client import BlizzardClient, BlizzardError
from .models import BlizzardRecord

pytestmark = pytest.mark.django_db


class FakeApi:
    """Transport httpx : jeton, puis routes Forever avec statuts choisis ; compte les appels."""

    def __init__(self):
        self.calls: list[str] = []
        self.flaky_left = 1  # statistics : un 503 puis 200
        self.token_requests = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == "oauth.battle.net":
            self.token_requests += 1
            assert request.headers["Authorization"].startswith("Basic ")
            return httpx.Response(
                200, json={"access_token": f"tok{self.token_requests}", "expires_in": 86399}
            )
        assert request.headers["Authorization"] == f"Bearer tok{self.token_requests}"
        self.calls.append(f"{url.path}?{url.params.get('namespace')}")
        path = url.path
        if path == "/data/wow/ruleset/index":
            return httpx.Response(200, json={"rulesets": [{"id": 1, "name": "Normal"}]})
        if path == "/profile/wow/character/thrall-fils-de-durotan":
            return httpx.Response(
                200, json={"name": "Thrall", "surname": "Fils-de-Durotan", "level": 60, "ruleset": {"id": 1}}
            )
        if path == "/profile/wow/character/thrall-fils-de-durotan/equipment":
            return httpx.Response(404, json={"code": 404, "detail": "Not Found"})
        if path == "/profile/wow/character/thrall-fils-de-durotan/statistics":
            if self.flaky_left:
                self.flaky_left -= 1
                return httpx.Response(503, headers={"Retry-After": "1"})
            return httpx.Response(200, json={"categories": [{"name": "Personnage", "sub_categories": []}]})
        if path.startswith("/profile/wow/character/thrall-fils-de-durotan/"):
            return httpx.Response(200, json={"ok": path.rsplit("/", 1)[-1], "items": [1, 2]})
        if path.startswith("/profile/wow/character/"):
            return httpx.Response(404, content=b"")
        if path == "/data/wow/guild/manuel-feralas":
            return httpx.Response(200, json={"name": "Manuel Feralas", "member_count": 12})
        if path == "/data/wow/guild/manuel-feralas/roster":
            return httpx.Response(
                200, json={"members": [{"character": {"name": "Thrall", "level": 60}, "rank": 0}]}
            )
        if path.startswith("/data/wow/guild/manuel-feralas/"):
            return httpx.Response(404, content=b"")
        if path == "/data/wow/playable-class/index":
            return httpx.Response(403, text="forbidden")
        return httpx.Response(500, text="boom")


def client(api: FakeApi, **kwargs) -> BlizzardClient:
    return BlizzardClient(
        "id",
        "secret",
        region="eu",
        transport=httpx.MockTransport(api.handler),
        sleep=lambda _: None,
        **kwargs,
    )


class TestClient:
    def test_namespaces_token_404_and_retries(self):
        api = FakeApi()
        c = client(api)
        assert c.namespace("profile") == "profile-forever-eu" and c.namespace("static") == "static-forever-eu"
        assert (
            client(api, static_version="1.60.1_70399").namespace("static") == "static-1.60.1_70399-forever-eu"
        )
        status, data = c.character("thrall-fils-de-durotan")
        assert status == 200 and data["surname"] == "Fils-de-Durotan"
        assert c.character("thrall-fils-de-durotan", "equipment") == (404, None)
        status, data = c.character("thrall-fils-de-durotan", "statistics")
        assert status == 200 and data["categories"][0]["name"] == "Personnage"  # après un 503
        assert api.token_requests == 1  # un seul jeton pour tout ça
        assert api.calls[0] == "/profile/wow/character/thrall-fils-de-durotan?profile-forever-eu"
        assert len([p for p in api.calls if p.endswith("/statistics?profile-forever-eu")]) == 2
        with pytest.raises(BlizzardError, match="403"):
            c.playable_classes()
        with pytest.raises(BlizzardError, match="500 sur data/wow/nothing"):
            c.get("data/wow/nothing", "dynamic")  # trois nouvelles tentatives, puis l'erreur
        assert len([p for p in api.calls if p.startswith("/data/wow/nothing")]) == 4
        with pytest.raises(BlizzardError, match="vides"):
            BlizzardClient("", "", transport=httpx.MockTransport(api.handler))

    def test_slugs(self):
        assert services.slugify("Manuel Feralas") == "manuel-feralas"
        assert services.slugify("  Les Fragiles  ") == "les-fragiles"


class TestArchive:
    @pytest.fixture(autouse=True)
    def gamedata(self, db):
        seed()

    def thrall(self, member):
        return Character.objects.create(
            owner=member,
            name="Thrall",
            surname="Fils-de-Durotan",
            player_class=PlayerClass.objects.get(slug="shaman"),
            race=Race.objects.get(slug="orc"),
            level=60,
            main_role="dps",
        )

    def test_fetch_all_archives_every_response_once_per_pass(self, member):
        thrall = self.thrall(member)
        Character.objects.create(
            owner=member,
            name="Alt",
            surname="",
            player_class=thrall.player_class,
            race=thrall.race,
            level=12,
            main_role="dps",
        )  # sans nom de famille : pas adressable
        unknown = Character.objects.create(
            owner=member,
            name="Inconnu",
            surname="Du-Site",
            player_class=thrall.player_class,
            race=thrall.race,
            level=5,
            main_role="dps",
        )
        GuildSettings.objects.update_or_create(
            pk=GuildSettings.SINGLETON_PK, defaults={"name": "Manuel Feralas"}
        )
        api = FakeApi()
        counts = services.fetch_all(client(api))
        assert counts == {"characters": 2, "found": 1, "missing": 1, "records": 12 + 4, "guild": 4}
        kinds = list(
            BlizzardRecord.objects.filter(character=thrall).order_by("pk").values_list("kind", "http_status")
        )
        assert kinds[0] == ("character/profile", 200) and ("character/equipment", 404) in kinds
        assert len(kinds) == len(services.CHARACTER_RESOURCES)
        assert BlizzardRecord.objects.filter(character=unknown).count() == 1  # fiche 404 : on s'arrête là
        roster = BlizzardRecord.objects.get(kind="guild/roster")
        assert roster.slug == "manuel-feralas" and roster.data["members"][0]["character"]["name"] == "Thrall"
        # Un second passage ajoute une lecture par ressource : c'est l'historique.
        services.fetch_all(client(api))
        assert BlizzardRecord.objects.filter(character=thrall, kind="character/profile").count() == 2

    def test_probe_command_prints_and_dumps(self, member, tmp_path, monkeypatch, settings):
        self.thrall(member)
        settings.BLIZZARD_CLIENT_ID, settings.BLIZZARD_CLIENT_SECRET = "id", "secret"
        api = FakeApi()
        monkeypatch.setattr(services, "client_from_settings", lambda: client(api))
        out = io.StringIO()
        call_command(
            "blizzard_probe",
            character="Thrall-Fils-de-Durotan",
            guild="manuel-feralas",
            dir=str(tmp_path),
            stdout=out,
        )
        text = out.getvalue()
        assert "rulesets (dynamic) : 200" in text and "character/profile thrall-fils-de-durotan : 200" in text
        assert (
            "character/equipment thrall-fils-de-durotan : 404" in text
            and "guild/roster manuel-feralas : 200" in text
        )
        dumped = json.loads(
            (tmp_path / "thrall-fils-de-durotan" / "character_profile.json").read_text(encoding="utf-8")
        )
        assert dumped["http_status"] == 200 and dumped["data"]["level"] == 60
        assert (tmp_path / "manuel-feralas" / "guild_roster.json").is_file()

    def test_commands_fail_cleanly_without_credentials(self, settings):
        settings.BLIZZARD_CLIENT_ID, settings.BLIZZARD_CLIENT_SECRET = "", ""
        with pytest.raises(Exception, match="BLIZZARD_CLIENT_ID"):
            call_command("blizzard_import")
