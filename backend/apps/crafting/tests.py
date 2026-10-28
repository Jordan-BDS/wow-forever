from pathlib import Path

import pytest

from apps.characters.models import Character, CharacterProfession, KnownRecipe
from apps.crafting.models import CraftRequest
from apps.gamedata.importer import import_directory
from apps.gamedata.models import PlayerClass, Profession, Race, Recipe
from apps.gamedata.seed import seed
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

SAMPLE = Path(__file__).resolve().parent.parent / "gamedata" / "fixtures" / "wago_sample"
MAJOR_MANA = 17580


@pytest.fixture
def world(db, member, other_member):
    seed()
    import_directory(SAMPLE, build="sample", product="wowf")
    alchemy = Profession.objects.get(slug="alchemy")
    crafter = Character.objects.create(
        owner=other_member, name="Alchimiste", player_class=PlayerClass.objects.get(slug="mage"),
        race=Race.objects.get(slug="undead"), level=60, main_role="dps", is_main=True,
    )  # fmt: skip
    CharacterProfession.objects.create(character=crafter, profession=alchemy, skill=300)
    KnownRecipe.objects.create(character=crafter, recipe_id=MAJOR_MANA)
    return {"crafter": crafter, "alchemy": alchemy}


class TestKnownRecipes:
    def test_put_requires_matching_profession(self, as_user, member, other_member, world):
        crafter = world["crafter"]
        client = as_user(other_member)
        url = f"/api/characters/{crafter.pk}/recipes/"
        assert client.get(url).data["recipes"] == [MAJOR_MANA]
        other = Recipe.objects.exclude(pk=MAJOR_MANA).first()
        assert client.put(url, {"recipes": [MAJOR_MANA, other.pk]}, format="json").status_code == 200
        assert client.put(url, {"recipes": [999999]}, format="json").status_code == 400
        assert client.put(url, {"recipes": []}, format="json").data["recipes"] == []
        assert as_user(member).put(url, {"recipes": []}, format="json").status_code == 403

    def test_auto_check_trainer_recipes(self, as_user, other_member, world):
        crafter = world["crafter"]
        Recipe.objects.filter(pk=MAJOR_MANA).update(acquire_method=3, min_skill=295)
        response = as_user(other_member).post(f"/api/characters/{crafter.pk}/recipes/")
        assert response.status_code == 200 and MAJOR_MANA in response.data["recipes"]
        crafter.professions.update(skill=100)
        KnownRecipe.objects.all().delete()
        response = as_user(other_member).post(f"/api/characters/{crafter.pk}/recipes/")
        assert MAJOR_MANA not in response.data["recipes"]  # 295 > 100

    def test_recipe_list_exposes_crafters(self, as_user, member, world):
        data = as_user(member).get("/api/recipes/", {"q": "mana majeure", "known": "1"}).data
        assert len(data) == 1
        crafter = data[0]["crafters"][0]
        assert crafter["name"] == "Alchimiste" and crafter["skill"] == 300 and crafter["owner_name"]


class TestCraftRequests:
    def test_lifecycle_with_notifications(self, as_user, member, other_member, world):
        crafter = world["crafter"]
        requester = as_user(member)
        created = requester.post(
            "/api/craft-requests/",
            {
                "recipe_id": MAJOR_MANA,
                "quantity": 5,
                "materials": "all",
                "note": "merci",
                "target_character_id": crafter.pk,
            },
            format="json",
        )
        assert created.status_code == 201, created.data
        craft_id = created.data["id"]
        assert created.data["status"] == "open" and created.data["target_character"]["name"] == "Alchimiste"
        kinds = list(Notification.objects.values_list("kind", "recipient_id"))
        assert ("craft_request", None) in kinds and ("craft_request", other_member.pk) in kinds

        taken = as_user(other_member).post(
            f"/api/craft-requests/{craft_id}/take/", {"character": crafter.pk}, format="json"
        )
        assert (
            taken.status_code == 200
            and taken.data["status"] == "taken"
            and taken.data["crafter"]["id"] == crafter.pk
        )
        assert Notification.objects.filter(kind="craft_update", recipient=member).count() == 1

        delivered = as_user(other_member).post(f"/api/craft-requests/{craft_id}/deliver/")
        assert delivered.status_code == 200 and delivered.data["status"] == "delivered"
        assert Notification.objects.filter(kind="craft_update", recipient=member).count() == 2
        assert requester.post(f"/api/craft-requests/{craft_id}/cancel/").status_code == 400  # déjà close

    def test_take_rules(self, as_user, member, other_member, officer, world):
        crafter = world["crafter"]
        craft_id = (
            as_user(member).post("/api/craft-requests/", {"recipe_id": MAJOR_MANA}, format="json").data["id"]
        )
        novice = Character.objects.create(
            owner=member, name="Novice", player_class=PlayerClass.objects.get(slug="mage"),
            race=Race.objects.get(slug="human"), level=10, main_role="dps", is_main=True,
        )  # fmt: skip
        assert (
            as_user(member)
            .post(f"/api/craft-requests/{craft_id}/take/", {"character": novice.pk}, format="json")
            .status_code
            == 400
        )
        assert (
            as_user(member)
            .post(f"/api/craft-requests/{craft_id}/take/", {"character": crafter.pk}, format="json")
            .status_code
            == 403
        )
        assert (
            as_user(officer)
            .post(f"/api/craft-requests/{craft_id}/take/", {"character": crafter.pk}, format="json")
            .status_code
            == 200
        )
        assert as_user(other_member).post(f"/api/craft-requests/{craft_id}/release/").status_code == 200
        from apps.notifications.models import Notification

        released = Notification.objects.filter(kind="craft_update", recipient=member).latest("pk")
        assert "de nouveau ouverte" in released.text and crafter.name in released.text
        assert CraftRequest.objects.get(pk=craft_id).status == "open"

    def test_target_must_know_recipe_and_scopes(self, as_user, member, other_member, world):
        crafter = world["crafter"]
        stranger = Character.objects.create(
            owner=member, name="Inconnu", player_class=PlayerClass.objects.get(slug="mage"),
            race=Race.objects.get(slug="human"), level=60, main_role="dps", is_main=True,
        )  # fmt: skip
        bad = as_user(member).post(
            "/api/craft-requests/",
            {"recipe_id": MAJOR_MANA, "target_character_id": stranger.pk},
            format="json",
        )
        assert bad.status_code == 400
        as_user(member).post("/api/craft-requests/", {"recipe_id": MAJOR_MANA}, format="json")
        assert len(as_user(member).get("/api/craft-requests/", {"scope": "mine"}).data) == 1
        assert len(as_user(other_member).get("/api/craft-requests/", {"scope": "doable"}).data) == 1
        assert len(as_user(member).get("/api/craft-requests/", {"scope": "doable"}).data) == 0
        assert len(as_user(member).get("/api/craft-requests/").data) == 1
        assert as_user(other_member).post("/api/craft-requests/1/cancel/").status_code == 403
        assert as_user(member).post("/api/craft-requests/1/cancel/").data["status"] == "cancelled"
        assert crafter.pk  # fixture utilisée


def test_bot_craft_search(world):
    from apps.discordbot.services import craft_search_text

    text = craft_search_text("mana majeure")
    assert "Potion de mana majeure" in text and "Alchimiste" in text
    assert "Aucune recette" in craft_search_text("zzzz")
