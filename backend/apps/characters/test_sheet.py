"""Fiche de personnage : sets d'équipement, stats, builds de talents (sur l'échantillon de données réel)."""

from pathlib import Path

import pytest

from apps.characters.models import Character, EquipmentSet, TalentBuild
from apps.gamedata.importer import import_directory
from apps.gamedata.models import Item, PlayerClass, Race, Talent, TalentTree
from apps.gamedata.seed import seed

pytestmark = pytest.mark.django_db

SAMPLE = Path(__file__).resolve().parent.parent / "gamedata" / "fixtures" / "wago_sample"
THUNDERFURY, RING, ASHBRINGER = 19019, 18821, 13262


@pytest.fixture
def mage(db, member):
    seed()
    import_directory(SAMPLE, build="sample", product="wowf")
    return Character.objects.create(
        owner=member,
        name="Jaina",
        player_class=PlayerClass.objects.get(slug="mage"),
        race=Race.objects.get(slug="human"),
        level=40,
        main_role="dps",
        is_main=True,
    )


@pytest.fixture
def warrior(db, member):
    seed()
    import_directory(SAMPLE, build="sample", product="wowf")
    return Character.objects.create(
        owner=member,
        name="Garrosh",
        player_class=PlayerClass.objects.get(slug="warrior"),
        race=Race.objects.get(slug="orc"),
        level=40,
        main_role="tank",
        is_main=False,
    )


def sets_url(character, suffix=""):
    return f"/api/characters/{character.pk}/equipment-sets/{suffix}"


class TestEquipmentSets:
    def test_first_set_is_primary_and_slots_are_validated(self, as_user, member, warrior):
        client = as_user(member)
        created = client.post(sets_url(warrior), {"name": "PvE"}, format="json")
        assert created.status_code == 201, created.data
        assert created.data["is_primary"] is True
        set_id = created.data["id"]

        response = client.put(
            sets_url(warrior, f"{set_id}/slots/"),
            {"slots": [{"slot": "main_hand", "item": THUNDERFURY}, {"slot": "finger1", "item": RING}]},
            format="json",
        )
        assert response.status_code == 200, response.data
        slots = {s["slot"]: s for s in response.data["slots"]}
        assert slots["main_hand"]["item"]["name_en"].startswith("Thunderfury")
        assert slots["main_hand"]["projected"] is True  # niveau 60 requis, perso niveau 40
        assert slots["finger1"]["projected"] is True

    def test_rejects_wrong_slot_class_and_duplicates(self, as_user, member, warrior, mage):
        client = as_user(member)
        set_id = client.post(sets_url(mage), {"name": "x"}, format="json").data["id"]
        wrong_slot = client.put(
            sets_url(mage, f"{set_id}/slots/"), {"slots": [{"slot": "head", "item": RING}]}, format="json"
        )
        assert wrong_slot.status_code == 400 and "head" in wrong_slot.data
        two_hand_on_mage = client.put(
            sets_url(mage, f"{set_id}/slots/"),
            {"slots": [{"slot": "main_hand", "item": ASHBRINGER}]},
            format="json",
        )
        assert (
            two_hand_on_mage.status_code == 400 and "main_hand" in two_hand_on_mage.data
        )  # un mage ne manie pas d'épée

        set_id = client.post(sets_url(warrior), {"name": "x"}, format="json").data["id"]
        twice = client.put(
            sets_url(warrior, f"{set_id}/slots/"),
            {"slots": [{"slot": "finger1", "item": RING}, {"slot": "finger2", "item": RING}]},
            format="json",
        )
        assert twice.status_code == 400 and "finger2" in twice.data
        two_hand = client.put(
            sets_url(warrior, f"{set_id}/slots/"),
            {"slots": [{"slot": "main_hand", "item": ASHBRINGER}, {"slot": "off_hand", "item": THUNDERFURY}]},
            format="json",
        )
        assert two_hand.status_code == 400 and "off_hand" in two_hand.data

    def test_stats_exclude_projected_items_and_preview_matches(self, as_user, member, warrior):
        client = as_user(member)
        set_id = client.post(sets_url(warrior), {"name": "x"}, format="json").data["id"]
        slots = [{"slot": "main_hand", "item": THUNDERFURY}, {"slot": "finger1", "item": RING}]
        client.put(sets_url(warrior, f"{set_id}/slots/"), {"slots": slots}, format="json")
        stats = client.get(sets_url(warrior, f"{set_id}/stats/")).data
        assert stats["totals"] == {} and sorted(stats["projected_slots"]) == ["finger1", "main_hand"]

        warrior.level = 60
        warrior.save()
        stats = client.get(sets_url(warrior, f"{set_id}/stats/")).data
        assert stats["totals"]["stamina"] == 16 and stats["totals"]["agility"] == 5
        assert stats["breakdown"]["stamina"] == {"items": 16}
        preview = client.post(sets_url(warrior, "preview/"), {"slots": slots}, format="json")
        assert preview.status_code == 200 and preview.data["totals"] == stats["totals"]

    def test_duplicate_primary_and_delete(self, as_user, member, warrior, other_member):
        client = as_user(member)
        first = client.post(sets_url(warrior), {"name": "PvE"}, format="json").data["id"]
        client.put(
            sets_url(warrior, f"{first}/slots/"),
            {"slots": [{"slot": "finger1", "item": RING}]},
            format="json",
        )
        copy = client.post(sets_url(warrior, f"{first}/duplicate/"))
        assert copy.status_code == 201 and copy.data["name"] == "PvE (copie)" and len(copy.data["slots"]) == 1
        assert copy.data["is_primary"] is False
        assert client.post(sets_url(warrior, f"{copy.data['id']}/set-primary/")).data["is_primary"] is True
        assert EquipmentSet.objects.filter(character=warrior, is_primary=True).count() == 1
        assert client.delete(sets_url(warrior, f"{copy.data['id']}/")).status_code == 204
        assert EquipmentSet.objects.get(pk=first).is_primary is True
        assert (
            as_user(other_member).post(sets_url(warrior), {"name": "pirate"}, format="json").status_code
            == 403
        )


class TestSingleSlot:
    def test_patch_one_slot_even_if_another_piece_is_now_invalid(self, as_user, member, warrior):
        client = as_user(member)
        set_id = client.post(sets_url(warrior), {"name": "x"}, format="json").data["id"]
        client.put(
            sets_url(warrior, f"{set_id}/slots/"),
            {"slots": [{"slot": "main_hand", "item": ASHBRINGER}]},
            format="json",
        )
        # Le guerrier devient mage : l'épée à deux mains n'est plus portable, mais on peut quand même agir.
        warrior.player_class = PlayerClass.objects.get(slug="mage")
        warrior.save()
        listing = client.get(sets_url(warrior)).data[0]
        assert listing["slots"][0]["error"]
        blocked = client.put(
            sets_url(warrior, f"{set_id}/slots/"),
            {"slots": [{"slot": "main_hand", "item": ASHBRINGER}, {"slot": "finger1", "item": RING}]},
            format="json",
        )
        assert blocked.status_code == 400
        patched = client.patch(
            sets_url(warrior, f"{set_id}/slot/"), {"slot": "finger1", "item": RING}, format="json"
        )
        assert patched.status_code == 200, patched.data
        assert {s["slot"] for s in patched.data["slots"]} == {"main_hand", "finger1"}
        emptied = client.patch(
            sets_url(warrior, f"{set_id}/slot/"), {"slot": "main_hand", "item": None}, format="json"
        )
        assert emptied.status_code == 200 and [s["slot"] for s in emptied.data["slots"]] == ["finger1"]

    def test_patch_keeps_cross_checks(self, as_user, member, warrior):
        client = as_user(member)
        set_id = client.post(sets_url(warrior), {"name": "x"}, format="json").data["id"]
        client.patch(sets_url(warrior, f"{set_id}/slot/"), {"slot": "finger1", "item": RING}, format="json")
        twice = client.patch(
            sets_url(warrior, f"{set_id}/slot/"), {"slot": "finger2", "item": RING}, format="json"
        )
        assert twice.status_code == 400 and "finger2" in twice.data
        client.patch(
            sets_url(warrior, f"{set_id}/slot/"), {"slot": "main_hand", "item": ASHBRINGER}, format="json"
        )
        off = client.patch(
            sets_url(warrior, f"{set_id}/slot/"), {"slot": "off_hand", "item": THUNDERFURY}, format="json"
        )
        assert off.status_code == 400 and "off_hand" in off.data


class TestTalentBuilds:
    def mage_points(self, count=6):
        """Les `count` premiers points dans le premier talent 5 rangs de l'arbre Feu puis un talent de
        rangée 1."""
        fire = TalentTree.objects.get(name="Feu")
        first = next(t for t in Talent.objects.filter(tree=fire, row=0).order_by("column") if t.max_rank == 5)
        second = Talent.objects.filter(tree=fire, row=1, prerequisite__isnull=True).order_by("column").first()
        return [first.id] * 5 + [second.id] * (count - 5)

    def test_create_validates_order_and_sets_specialization(self, as_user, member, mage):
        client = as_user(member)
        url = f"/api/characters/{mage.pk}/talent-builds/"
        bad = client.post(url, {"name": "Raté", "points": self.mage_points()[::-1]}, format="json")
        assert bad.status_code == 400 and "points" in bad.data
        good = client.post(url, {"name": "Feu", "points": self.mage_points()}, format="json")
        assert good.status_code == 201, good.data
        assert good.data["is_active"] is True and good.data["acquired"] == 6
        mage.refresh_from_db()
        assert mage.specialization.slug == "mage-fire"

    def test_projected_points_beyond_level(self, as_user, member, mage):
        mage.level = 12  # 3 points acquis
        mage.save()
        client = as_user(member)
        response = client.post(
            f"/api/characters/{mage.pk}/talent-builds/",
            {"name": "Lvl", "points": self.mage_points()},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["acquired"] == 3 and len(response.data["points"]) == 6

    def test_activate_switches_and_other_class_talent_rejected(self, as_user, member, mage, warrior):
        client = as_user(member)
        url = f"/api/characters/{mage.pk}/talent-builds/"
        a = client.post(url, {"name": "A", "points": self.mage_points()}, format="json").data["id"]
        b = client.post(url, {"name": "B", "points": []}, format="json").data
        assert b["is_active"] is False
        assert client.post(f"{url}{b['id']}/activate/").data["is_active"] is True
        assert TalentBuild.objects.get(pk=a).is_active is False
        arms = Talent.objects.filter(tree__player_class__slug="warrior").first()
        if arms:  # l'échantillon ne contient que le mage, mais le contrôle est quand même là
            assert client.post(url, {"name": "x", "points": [arms.id]}, format="json").status_code == 400
        assert client.post(url, {"name": "x", "points": [999999]}, format="json").status_code == 400

    def test_too_many_points(self, as_user, member, mage):
        response = as_user(member).post(
            f"/api/characters/{mage.pk}/talent-builds/", {"name": "x", "points": [1] * 52}, format="json"
        )
        assert response.status_code == 400


def test_sample_has_items(mage):
    assert Item.objects.filter(pk=THUNDERFURY).exists()
