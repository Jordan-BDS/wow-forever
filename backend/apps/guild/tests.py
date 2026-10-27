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


def test_rejects_unknown_faction(as_user, gm):
    response = as_user(gm).patch("/api/guild/", {"faction": "scourge"}, format="json")
    assert response.status_code == 400


def test_singleton_never_duplicates(db):
    GuildSettings(name="A").save()
    GuildSettings(name="B").save()
    assert GuildSettings.objects.count() == 1
    assert GuildSettings.load().name == "B"
