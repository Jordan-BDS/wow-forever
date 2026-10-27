from pathlib import Path

import pytest

from apps.gamedata.importer import import_directory
from apps.gamedata.models import (
    Enchantment,
    Item,
    PlayerClass,
    Race,
    Recipe,
    Specialization,
    Talent,
    TalentTree,
)
from apps.gamedata.seed import seed  # noqa: E402

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


def test_instances_are_seeded_with_default_needs(as_user, member):
    seed()
    response = as_user(member).get("/api/gamedata/")
    instances = response.data["instances"]
    assert len(instances) == 30
    mc = next(i for i in instances if i["slug"] == "molten-core")
    assert (mc["kind"], mc["size"], mc["default_tanks"], mc["default_heals"], mc["default_dps"]) == (
        "raid",
        40,
        4,
        10,
        26,
    )
    wsg = next(i for i in instances if i["slug"] == "warsong-gulch")
    assert wsg["default_tanks"] is None


SAMPLE = Path(__file__).resolve().parent / "fixtures" / "wago_sample"


@pytest.fixture
def imported(db):
    seed()
    return import_directory(SAMPLE, build="sample", product="wowf")


class TestImporter:
    def test_counts_and_idempotence(self, imported):
        assert {k: v for k, v in imported.counts.items() if k != "items"} == {
            "item_sets": 1, "enchantments": 2, "talent_trees": 3, "talents": 49, "recipes": 2,
        }  # fmt: skip
        assert imported.counts["items"] == Item.objects.count() > 10
        again = import_directory(SAMPLE, build="sample", product="wowf")
        assert again.counts == imported.counts

    def test_item_stats_are_decoded_from_budget_percentages(self, imported):
        thunderfury = Item.objects.get(pk=19019)
        assert thunderfury.name_en == "Thunderfury, Blessed Blade of the Windseeker"
        assert thunderfury.quality == 5 and thunderfury.is_unique
        assert thunderfury.stats == {"agility": 5, "stamina": 8, "fire_resistance": 8, "nature_resistance": 9}
        assert thunderfury.icon == "inv_sword_39"
        ring = Item.objects.get(pk=18821)
        assert ring.stats == {"stamina": 8, "strength": 5, "crit_rating": 14, "attack_power": 30}

    def test_item_sets_and_bonuses(self, imported):
        piece = Item.objects.filter(item_set__isnull=False).first()
        assert piece.item_set.name == "Armure volcanique"
        assert piece.item_set.items.count() >= 3
        assert [b["threshold"] for b in piece.item_set.bonuses] == [3]
        assert all(b["spell_id"] for b in piece.item_set.bonuses)

    def test_talents_with_prerequisites(self, imported):
        trees = list(TalentTree.objects.filter(player_class__slug="mage").values_list("name", flat=True))
        assert sorted(trees) == ["Arcanes", "Feu", "Givre"]
        with_prereq = Talent.objects.filter(prerequisite__isnull=False)
        assert with_prereq.exists()
        talent = with_prereq.first()
        assert talent.prerequisite.tree_id == talent.tree_id
        assert talent.max_rank >= 1 and talent.icon

    def test_recipes_with_product_and_reagents(self, imported):
        potion = Recipe.objects.get(pk=17580)
        assert potion.icon == potion.product.icon != ""  # icône du sort = TEMP.BLP → celle de la potion
        assert potion.profession.slug == "alchemy"
        assert potion.product.name_en == "Major Mana Potion" and potion.quantity == 1
        assert (potion.min_skill, potion.skill_yellow, potion.skill_grey) == (295, 310, 350)
        greater = Recipe.objects.get(pk=17553)
        assert greater.min_skill == greater.skill_yellow - 15 and greater.product
        assert all(r["count"] >= 1 and r["name"] for r in potion.reagents)
        assert len(potion.reagents) >= 2

    def test_enchantments_carry_stats_and_slot_mask(self, imported):
        healing = Enchantment.objects.get(pk=2505)
        assert healing.stats == {"spell_healing": 55, "spell_damage": 19}
        assert healing.spell_id == 22750 and healing.equipped_class == 2  # une arme
        crusader = Enchantment.objects.get(pk=1900)
        assert crusader.name and crusader.spell_id

    def test_manual_forever_rows_survive_reimport(self, imported):
        Item.objects.create(id=999999, name="Objet Forever", is_forever=True)
        Item.objects.filter(pk=19019).update(is_forever=True, name="Renommé")
        import_directory(SAMPLE, build="sample", product="wowf")
        assert Item.objects.get(pk=999999).name == "Objet Forever"
        assert Item.objects.get(pk=19019).name == "Renommé"


class TestIndexApi:
    def test_item_search_by_french_or_english_name_and_slot(self, imported, as_user, member):
        client = as_user(member)
        assert [i["id"] for i in client.get("/api/items/", {"q": "thunderfury"}).data] == [19019]
        assert [i["id"] for i in client.get("/api/items/", {"q": "lame-tonnerre"}).data] == [19019]
        rings = client.get("/api/items/", {"slot": "finger"}).data
        assert [i["id"] for i in rings] == [18821] and rings[0]["slot"] == "finger"
        assert rings[0]["icon_url"].endswith(".jpg")

    def test_item_detail_includes_set(self, imported, as_user, member):
        piece = Item.objects.filter(item_set__isnull=False).first()
        data = as_user(member).get(f"/api/items/{piece.pk}/").data
        assert data["item_set"]["name"] == "Armure volcanique" and piece.pk in data["item_set"]["item_ids"]

    def test_class_talents(self, imported, as_user, member):
        data = as_user(member).get("/api/talents/mage/").data
        assert len(data["trees"]) == 3 and sum(len(t["talents"]) for t in data["trees"]) == 49
        assert as_user(member).get("/api/talents/nope/").status_code == 404

    def test_recipes_and_enchantments(self, imported, as_user, member):
        client = as_user(member)
        assert len(client.get("/api/recipes/", {"profession": "alchemy"}).data) == 2
        assert client.get("/api/recipes/", {"q": "mana majeure"}).data[0]["source"] == ""
        assert len(client.get("/api/recipes/", {"q": "Major Mana"}).data) == 1
        assert len(client.get("/api/enchantments/").data) == 2
        assert client.get("/api/gamedata/").data["import_run"]["build"] == "sample"
