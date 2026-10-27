import pytest

from apps.gamedata.models import PlayerClass, Race, Specialization
from apps.gamedata.seed import seed

pytestmark = pytest.mark.django_db


def test_seed_is_idempotent():
    seed()
    counts = (PlayerClass.objects.count(), Specialization.objects.count(), Race.objects.count())
    seed()
    assert (PlayerClass.objects.count(), Specialization.objects.count(), Race.objects.count()) == counts
    assert counts == (9, 27, 9)


def test_class_roles_derive_from_specializations():
    seed()
    assert PlayerClass.objects.get(slug="druid").roles == ["tank", "heal", "dps"]
    assert PlayerClass.objects.get(slug="mage").roles == ["dps"]
    assert PlayerClass.objects.get(slug="priest").roles == ["heal", "dps"]


def test_race_faction_availability():
    seed()
    skyborn = Race.objects.get(slug="skyborn")
    orc = Race.objects.get(slug="orc")
    assert skyborn.available_for("alliance") and skyborn.available_for("horde")
    assert orc.available_for("horde") and not orc.available_for("alliance")
    assert orc.available_for("")  # faction de guilde pas encore choisie


def test_gamedata_endpoint(as_user, member):
    seed()
    response = as_user(member).get("/api/gamedata/")
    assert response.status_code == 200
    druid = next(c for c in response.data["classes"] if c["slug"] == "druid")
    assert druid["color"] == "#FF7C0A"
    assert [s["slug"] for s in druid["specializations"]] == [
        "druid-balance",
        "druid-feral",
        "druid-restoration",
    ]
    tauren = next(r for r in response.data["races"] if r["slug"] == "tauren")
    assert set(tauren["classes"]) == {"warrior", "hunter", "shaman", "druid"}
    assert len(response.data["professions"]) == 12
