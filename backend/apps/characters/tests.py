import pytest

from apps.characters.models import Character
from apps.gamedata.seed import seed
from apps.guild.models import GuildSettings

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def gamedata(db):
    seed()


def payload(**overrides):
    base = {
        "name": "Thrall",
        "player_class": "shaman",
        "race": "orc",
        "level": 42,
        "main_role": "heal",
        "off_role": "dps",
        "specialization": "shaman-restoration",
        "professions": [
            {"profession": "alchemy", "skill": 225},
            {"profession": "herbalism", "skill": 300},
            {"profession": "cooking", "skill": 75},
        ],
    }
    return {**base, **overrides}


def create(client, **overrides):
    return client.post("/api/characters/", payload(**overrides), format="json")


class TestCreate:
    def test_creates_and_first_character_becomes_main(self, as_user, member):
        response = create(as_user(member))
        assert response.status_code == 201, response.data
        assert response.data["is_main"] is True
        assert response.data["owner"]["id"] == member.pk
        assert [p["profession"] for p in response.data["professions"]] == ["alchemy", "herbalism", "cooking"]

    def test_second_character_is_an_alt_unless_marked_main(self, as_user, member):
        client = as_user(member)
        first = create(client).data
        second = create(
            client,
            name="Garrosh",
            player_class="warrior",
            main_role="tank",
            off_role="dps",
            specialization="warrior-protection",
            professions=[],
        ).data
        assert second["is_main"] is False
        third = create(
            client,
            name="Rexxar",
            player_class="hunter",
            main_role="dps",
            off_role="",
            specialization=None,
            professions=[],
            is_main=True,
        ).data
        assert third["is_main"] is True
        assert Character.objects.get(pk=first["id"]).is_main is False
        assert Character.objects.filter(owner=member, is_main=True).count() == 1

    def test_name_is_unique_case_insensitive(self, as_user, member, other_member):
        create(as_user(member))
        response = create(as_user(other_member), name="thrall")
        assert response.status_code == 400
        assert "name" in response.data

    def test_rejects_incompatible_race_and_class(self, as_user, member):
        response = create(
            as_user(member),
            race="tauren",
            player_class="rogue",
            main_role="dps",
            off_role="",
            specialization=None,
        )
        assert response.status_code == 400
        assert "race" in response.data

    def test_rejects_role_the_class_cannot_fill(self, as_user, member):
        response = create(
            as_user(member),
            player_class="mage",
            race="undead",
            main_role="tank",
            off_role="",
            specialization=None,
        )
        assert response.status_code == 400
        assert "main_role" in response.data

    def test_rejects_specialization_of_another_class(self, as_user, member):
        response = create(as_user(member), specialization="mage-fire")
        assert response.status_code == 400
        assert "specialization" in response.data

    def test_rejects_same_main_and_off_role(self, as_user, member):
        response = create(as_user(member), off_role="heal")
        assert response.status_code == 400
        assert "off_role" in response.data

    def test_rejects_three_primary_professions(self, as_user, member):
        response = create(
            as_user(member),
            professions=[
                {"profession": "alchemy", "skill": 1},
                {"profession": "herbalism", "skill": 1},
                {"profession": "mining", "skill": 1},
            ],
        )
        assert response.status_code == 400
        assert "professions" in response.data

    def test_rejects_profession_specialization_mismatch(self, as_user, member):
        response = create(
            as_user(member),
            professions=[
                {"profession": "alchemy", "skill": 1, "specialization": "engineering-gnomish"},
            ],
        )
        assert response.status_code == 400

    def test_accepts_profession_specialization(self, as_user, member):
        response = create(
            as_user(member),
            professions=[
                {"profession": "engineering", "skill": 300, "specialization": "engineering-gnomish"},
            ],
        )
        assert response.status_code == 201, response.data
        assert response.data["professions"][0]["specialization"] == "engineering-gnomish"

    def test_race_must_match_guild_faction(self, as_user, member):
        settings = GuildSettings.load()
        settings.faction = "alliance"
        settings.save()
        assert create(as_user(member)).status_code == 400
        ok = create(
            as_user(member),
            race="skyborn-alliance",
            player_class="druid",
            main_role="heal",
            off_role="",
            specialization=None,
        )
        assert ok.status_code == 201, ok.data

    def test_level_bounds(self, as_user, member):
        assert create(as_user(member), level=61).status_code == 400
        assert create(as_user(member), level=0).status_code == 400

    def test_officer_can_create_for_someone_else_but_member_cannot(
        self, as_user, member, officer, other_member
    ):
        denied = create(as_user(member), owner_id=other_member.pk)
        assert denied.status_code == 403
        allowed = create(as_user(officer), owner_id=other_member.pk)
        assert allowed.status_code == 201
        assert allowed.data["owner"]["id"] == other_member.pk


class TestUpdateAndDelete:
    def test_owner_updates_level_and_professions(self, as_user, member):
        client = as_user(member)
        created = create(client).data
        response = client.patch(
            f"/api/characters/{created['id']}/",
            {"level": 60, "professions": [{"profession": "alchemy", "skill": 300}]},
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data["level"] == 60
        assert len(response.data["professions"]) == 1

    def test_other_member_cannot_edit_but_officer_can(self, as_user, member, other_member, officer):
        created = create(as_user(member)).data
        assert (
            as_user(other_member).patch(f"/api/characters/{created['id']}/", {"level": 2}).status_code == 403
        )
        assert as_user(officer).patch(f"/api/characters/{created['id']}/", {"level": 2}).status_code == 200

    def test_set_main_switches_main(self, as_user, member):
        client = as_user(member)
        first = create(client).data
        second = create(
            client,
            name="Alt",
            player_class="mage",
            race="troll",
            main_role="dps",
            off_role="",
            specialization=None,
            professions=[],
        ).data
        response = client.post(f"/api/characters/{second['id']}/set-main/")
        assert response.status_code == 200
        assert response.data["is_main"] is True
        assert Character.objects.get(pk=first["id"]).is_main is False

    def test_deleting_main_promotes_highest_alt(self, as_user, member):
        client = as_user(member)
        main = create(client).data
        alt = create(
            client,
            name="Alt",
            player_class="mage",
            race="troll",
            level=30,
            main_role="dps",
            off_role="",
            specialization=None,
            professions=[],
        ).data
        assert client.delete(f"/api/characters/{main['id']}/").status_code == 204
        assert Character.objects.get(pk=alt["id"]).is_main is True

    def test_list_hides_characters_of_deactivated_members(self, as_user, member, other_member):
        create(as_user(member))
        other_member.is_active = False
        other_member.save()
        from apps.gamedata.models import PlayerClass, Race

        Character.objects.create(
            owner=other_member,
            name="Fantôme",
            player_class=PlayerClass.objects.get(slug="warrior"),
            race=Race.objects.get(slug="orc"),
            level=1,
            main_role="dps",
        )
        response = as_user(member).get("/api/characters/")
        assert [c["name"] for c in response.data] == ["Thrall"]
