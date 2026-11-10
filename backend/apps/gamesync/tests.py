from datetime import timedelta

import pytest
from django.utils import timezone

from apps.characters.models import Character, CharacterProfession, TalentBuild
from apps.gamedata.models import Item, PlayerClass, Profession, Race, Recipe, Talent, TalentTree
from apps.gamedata.seed import seed
from apps.guild.models import GuildSettings

from . import services
from .format import ExportError, decode_export, encode_export
from .models import CharacterSnapshot, IgnoredCharacter, ImportBatch, PairingCode

pytestmark = pytest.mark.django_db

NOW = timezone.now()


@pytest.fixture(autouse=True)
def gamedata(db):
    seed()
    alchemy = Profession.objects.get(slug="alchemy")
    Recipe.objects.create(id=17580, profession=alchemy, name="Potion de mana majeure", min_skill=295)
    Recipe.objects.create(id=11448, profession=alchemy, name="Potion de mana supérieure", min_skill=205)


def character_payload(**overrides):
    base = {
        "guid": "Player-1-000ABC01",
        "name": "Thrall",
        "surname": "Fils-de-Durotan",
        "realm": "Forever",
        "class": "SHAMAN",
        "race": "Orc",
        "level": 60,
        "spec": "enhancement",
        "exported_at": int(NOW.timestamp()),
        "professions": [
            {"id": 171, "skill": 300, "recipes": [17580, 11448, 99999]},
            {"id": 186, "skill": 275},
        ],
    }
    return {**base, **overrides}


def export_code(*characters, **extra):
    payload = {"v": 1, "addon": "0.1.0", "install": "inst-1", "characters": list(characters)}
    payload.update(extra)
    return encode_export(payload)


def do_import(client, code):
    return client.post("/api/sync/import/", {"code": code}, format="json")


class TestFormat:
    def test_round_trip_and_whitespace_tolerance(self):
        code = export_code(character_payload())
        assert code.startswith("WFG1:")
        wrapped = "\n".join(code[i : i + 60] for i in range(0, len(code), 60))
        assert decode_export(wrapped)["characters"][0]["name"] == "Thrall"

    def test_errors_are_explicit(self):
        code = export_code(character_payload())
        with pytest.raises(ExportError, match="commencer par « WFG »"):
            decode_export("bonjour")
        with pytest.raises(ExportError, match="incomplet"):
            decode_export(code[:-15])
        with pytest.raises(ExportError, match="plus récente"):
            decode_export("WFG9" + code[4:])
        prefix, checksum, data = code.split(":")
        with pytest.raises(ExportError, match="somme de contrôle"):
            decode_export(f"{prefix}:{'0' * 8}:{data}")
        with pytest.raises(ExportError, match="aucun personnage"):
            decode_export(encode_export({"v": 1}))

    def test_zlib_bomb_is_refused_but_normal_export_passes(self):
        # 20 Mo de « a » tiennent dans quelques Ko compressés : sans borne, le serveur gonflerait en mémoire.
        bomb = encode_export({"v": 1, "characters": [{"blob": "a" * 20_000_000}]})
        assert len(bomb) < 256 * 1024
        with pytest.raises(ExportError, match="trop volumineux"):
            decode_export(bomb)
        assert decode_export(export_code(character_payload()))["characters"][0]["name"] == "Thrall"


class TestPairing:
    def test_code_then_token_then_import(self, as_user, member, api_client):
        response = as_user(member).post("/api/sync/pairing-code/")
        assert response.status_code == 201
        code = response.data["code"]
        assert len(code) == 6 and PairingCode.objects.filter(code=code, user=member).exists()

        api_client.force_authenticate(None)
        paired = api_client.post(
            "/api/sync/pair/", {"code": code.lower(), "device_name": "PC de Jordan"}, format="json"
        )
        assert paired.status_code == 201, paired.data
        token = paired.data["token"]
        assert paired.data["display_name"] == member.display_name
        assert (
            api_client.post("/api/sync/pair/", {"code": code}, format="json").status_code == 400
        )  # usage unique

        api_client.credentials(HTTP_AUTHORIZATION=f"Companion {token}")
        # État fusionné pour la complétion d'un autre PC : vide tant qu'aucun personnage n'est importé.
        empty = api_client.get("/api/sync/state/")
        assert empty.status_code == 200 and empty.data["characters"] == [] and empty.data["seed_at"] > 0
        assert empty.data["wanted"] == []
        me = api_client.get("/api/sync/companion/me/")
        assert (
            me.status_code == 200
            and me.data["device"]["name"] == "PC de Jordan"
            and me.data["last_import"] is None
        )
        imported = do_import(api_client, export_code(character_payload()))
        assert imported.status_code == 201, imported.data
        assert imported.data["source"] == "companion" and imported.data["device"]["name"] == "PC de Jordan"
        assert Character.objects.get(guid="Player-1-000ABC01").owner == member
        # L'état servi au compagnon désigne l'export compris (base) et le conserve.
        state = api_client.get("/api/sync/state/")
        (served,) = state.data["characters"]
        assert served["guid"] == "Player-1-000ABC01" and served["class"] == "SHAMAN"
        assert served["counters"] == {} and served["bases"] == {"inst-1": int(NOW.timestamp())}
        assert CharacterSnapshot.objects.get(guid="Player-1-000ABC01").kept is True

        api_client.credentials()
        as_user(member).post(f"/api/sync/devices/{paired.data['device']['id']}/revoke/")
        api_client.force_authenticate(None)
        api_client.credentials(HTTP_AUTHORIZATION=f"Companion {token}")
        assert api_client.get("/api/sync/companion/me/").status_code == 401

    def test_expired_or_unknown_code(self, member, api_client):
        pairing = services.create_pairing_code(member)
        PairingCode.objects.filter(pk=pairing.pk).update(expires_at=NOW - timedelta(minutes=1))
        response = api_client.post("/api/sync/pair/", {"code": pairing.code}, format="json")
        assert response.status_code == 400 and "expiré" in str(response.data["code"])
        assert api_client.post("/api/sync/pair/", {"code": "ZZZZZZ"}, format="json").status_code == 400

    def test_new_code_invalidates_previous(self, member):
        first = services.create_pairing_code(member)
        services.create_pairing_code(member)
        first.refresh_from_db()
        assert first.expires_at <= timezone.now()


class TestImport:
    def test_creates_unknown_character_with_professions_and_recipes(self, as_user, member):
        response = do_import(as_user(member), export_code(character_payload()))
        assert response.status_code == 201, response.data
        assert response.data["summary"]["created"] == 1 and response.data["summary"]["new_recipes"] == 2
        (line,) = response.data["snapshots"]
        assert (
            line["status"] == "created"
            and line["full_name"] == "Thrall Fils-de-Durotan"
            and line["level"] == 60
        )
        character = Character.objects.get(guid="Player-1-000ABC01")
        assert (character.owner, character.level, character.is_main, character.roles_confirmed) == (
            member,
            60,
            True,
            False,
        )
        assert character.source == "addon" and character.main_role == "dps"  # amélioration → dps
        assert sorted(character.professions.values_list("profession__slug", "skill")) == [
            ("alchemy", 300),
            ("mining", 275),
        ]
        assert set(character.known_recipes.values_list("recipe_id", flat=True)) == {
            17580,
            11448,
        }  # 99999 inconnue ignorée

    def test_default_role_follows_the_talent_tab(self, as_user, member):
        payload = character_payload(
            guid="Player-1-0007", name="Soigneur", spec="", spec_tab=3
        )  # restauration
        do_import(as_user(member), export_code(payload))
        assert Character.objects.get(guid="Player-1-0007").main_role == "heal"

    def test_matches_by_guid_then_by_name_and_replaces_professions(self, as_user, member):
        existing = Character.objects.create(
            owner=member, name="Thrall", player_class=PlayerClass.objects.get(slug="shaman"),
            race=Race.objects.get(slug="orc"), level=40, main_role="heal", is_main=True,
        )  # fmt: skip
        CharacterProfession.objects.create(
            character=existing, profession=Profession.objects.get(slug="cooking"), skill=10
        )
        response = do_import(as_user(member), export_code(character_payload(level=58)))
        assert response.data["snapshots"][0]["status"] == "applied"
        existing.refresh_from_db()
        assert (existing.guid, existing.level, existing.surname, existing.main_role) == (
            "Player-1-000ABC01",
            58,
            "Fils-de-Durotan",
            "heal",
        )
        assert sorted(existing.professions.values_list("profession__slug", flat=True)) == [
            "alchemy",
            "mining",
        ]  # cuisine abandonnée

        later = do_import(
            as_user(member), export_code(character_payload(level=59, exported_at=int(NOW.timestamp()) + 60))
        )
        assert (
            later.data["snapshots"][0]["status"] == "applied"
            and later.data["snapshots"][0]["character"]["id"] == existing.pk
        )
        existing.refresh_from_db()
        assert existing.level == 59

    def test_stale_export_and_duplicate_code_are_ignored(self, as_user, member):
        client = as_user(member)
        code = export_code(character_payload())
        assert do_import(client, code).status_code == 201
        duplicate = do_import(client, code)
        assert duplicate.status_code == 409 and "déjà" in duplicate.data["detail"]
        older = do_import(
            client, export_code(character_payload(level=12, exported_at=int(NOW.timestamp()) - 3600))
        )
        assert older.data["snapshots"][0]["status"] == "stale"
        assert Character.objects.get(guid="Player-1-000ABC01").level == 60

    def test_future_export_date_is_capped_to_now(self, as_user, member):
        client = as_user(member)
        future = int((timezone.now() + timedelta(days=2)).timestamp())
        response = do_import(client, export_code(character_payload(exported_at=future)))
        assert response.data["snapshots"][0]["status"] == "created"
        character = Character.objects.get(guid="Player-1-000ABC01")
        assert abs(character.last_synced_at - timezone.now()) < timedelta(minutes=1)
        # Un export normal postérieur n'est pas « stale » : l'horloge en avance n'a pas bloqué les imports
        later = do_import(
            client, export_code(character_payload(level=59, exported_at=int(timezone.now().timestamp()) + 60))
        )
        assert later.data["snapshots"][0]["status"] == "applied"
        assert Character.objects.get(guid="Player-1-000ABC01").level == 59

    def test_absurd_export_date_is_refused_not_fatal(self, as_user, member):
        response = do_import(as_user(member), export_code(character_payload(exported_at=1e20)))
        assert response.status_code == 201
        (line,) = response.data["snapshots"]
        assert line["status"] == "refused" and "date d'export invalide" in line["note"]
        assert not Character.objects.filter(guid="Player-1-000ABC01").exists()

    def test_refuses_character_of_another_player_and_homonyms(self, as_user, member, other_member):
        do_import(as_user(other_member), export_code(character_payload()))
        response = do_import(
            as_user(member),
            export_code(character_payload(), character_payload(guid="Player-1-0002", name="Garona")),
        )
        statuses = {s["name"]: s for s in response.data["snapshots"]}
        assert (
            statuses["Thrall"]["status"] == "refused"
            and other_member.display_name in statuses["Thrall"]["note"]
        )
        assert statuses["Garona"]["status"] == "created"
        # Homonyme sans GUID chez un autre joueur : pas de création silencieuse
        Character.objects.create(
            owner=other_member, name="Cairne", player_class=PlayerClass.objects.get(slug="druid"),
            race=Race.objects.get(slug="tauren"), level=20, main_role="dps",
        )  # fmt: skip
        response = do_import(
            as_user(member),
            export_code(
                character_payload(guid="Player-1-0003", name="Cairne", **{"class": "DRUID", "race": "Tauren"})
            ),
        )
        assert response.data["snapshots"][0]["status"] == "refused"
        # Même prénom, autre nom de famille (reroll d'un membre, ou un autre joueur) : créé, Forever donne
        # un nom de famille. Même prénom et même nom chez un autre joueur : refusé.
        response = do_import(
            as_user(member),
            export_code(
                character_payload(guid="Player-1-0004", name="Thrall", surname="Fils-de-Personne"),
                character_payload(guid="Player-1-0005", name="Thrall", surname="Fils-de-Durotan"),
            ),
        )
        statuses = {s["guid"]: s for s in response.data["snapshots"]}
        assert statuses["Player-1-0004"]["status"] == "created"
        assert (
            statuses["Player-1-0005"]["status"] == "refused"
            and "Fils-de-Durotan" in statuses["Player-1-0005"]["note"]
        )
        assert Character.objects.filter(name="Thrall").count() == 2

    def test_candidate_goes_pending_then_merge(self, as_user, member):
        candidate = Character.objects.create(
            owner=member, name="Thrallou", player_class=PlayerClass.objects.get(slug="shaman"),
            race=Race.objects.get(slug="orc"), level=40, main_role="heal", is_main=True,
        )  # fmt: skip
        response = do_import(as_user(member), export_code(character_payload()))
        (line,) = response.data["snapshots"]
        assert (
            line["status"] == "pending"
            and line["candidate"]["id"] == candidate.pk
            and "Thrallou" in line["note"]
        )
        assert not Character.objects.filter(guid="Player-1-000ABC01").exists()

        pending = as_user(member).get("/api/sync/pending/")
        assert [p["id"] for p in pending.data] == [line["id"]]
        resolved = as_user(member).post(
            f"/api/sync/pending/{line['id']}/resolve/", {"action": "merge"}, format="json"
        )
        assert resolved.status_code == 200, resolved.data
        candidate.refresh_from_db()
        assert (candidate.guid, candidate.level, candidate.name) == ("Player-1-000ABC01", 60, "Thrallou")
        assert as_user(member).get("/api/sync/pending/").data == []

    def test_pending_create_and_ignore(self, as_user, member):
        Character.objects.create(
            owner=member, name="Autre", player_class=PlayerClass.objects.get(slug="shaman"),
            race=Race.objects.get(slug="orc"), level=40, main_role="heal", is_main=True,
        )  # fmt: skip
        client = as_user(member)
        line = do_import(client, export_code(character_payload())).data["snapshots"][0]
        created = client.post(f"/api/sync/pending/{line['id']}/resolve/", {"action": "create"}, format="json")
        assert created.status_code == 200 and created.data["status"] == "created"
        assert Character.objects.filter(guid="Player-1-000ABC01", name="Thrall", is_main=False).exists()

        line = do_import(
            client, export_code(character_payload(guid="Player-1-0009", name="Durotan", level=30))
        ).data["snapshots"][0]
        assert line["status"] == "pending"
        ignored = client.post(f"/api/sync/pending/{line['id']}/resolve/", {"action": "ignore"}, format="json")
        assert (
            ignored.data["status"] == "ignored"
            and IgnoredCharacter.objects.filter(user=member, guid="Player-1-0009").exists()
        )
        again = do_import(
            client, export_code(character_payload(guid="Player-1-0009", name="Durotan", level=31))
        )
        assert (
            again.data["snapshots"][0]["status"] == "ignored" and client.get("/api/sync/pending/").data == []
        )

    def test_low_level_ignored_by_default_but_can_be_included(self, as_user, member, monkeypatch):
        monkeypatch.setattr(
            services, "MIN_LEVEL_BY_DEFAULT", 10
        )  # désactivé pour la sortie (tout le monde est niveau 1)
        client = as_user(member)
        line = do_import(
            client, export_code(character_payload(guid="Player-1-0004", name="Banquo", level=4))
        ).data["snapshots"][0]
        assert line["status"] == "ignored" and line["low_level"] is True
        pending = client.get("/api/sync/pending/").data
        assert pending[0]["low_level"] is True
        included = client.post(
            f"/api/sync/pending/{line['id']}/resolve/", {"action": "create"}, format="json"
        )
        assert (
            included.data["status"] == "created" and Character.objects.filter(name="Banquo", level=4).exists()
        )

    def test_invalid_entries_are_refused_not_fatal(self, as_user, member):
        response = do_import(
            as_user(member), export_code({"guid": "x"}, "n'importe quoi", character_payload(level=99))
        )
        assert response.status_code == 201
        assert [s["status"] for s in response.data["snapshots"]] == ["refused"] * 3
        assert response.data["summary"]["refused"] == 3

    def test_snapshots_keep_one_per_day_and_history_endpoint(self, as_user, member):
        client = as_user(member)
        do_import(client, export_code(character_payload(level=58)))
        do_import(client, export_code(character_payload(level=59, exported_at=int(NOW.timestamp()) + 30)))
        character = Character.objects.get(guid="Player-1-000ABC01")
        assert CharacterSnapshot.objects.filter(character=character).count() == 1
        assert CharacterSnapshot.objects.get(character=character).data["level"] == 59
        history = client.get("/api/sync/imports/")
        assert history.status_code == 200 and len(history.data) == 2 and ImportBatch.objects.count() == 2

    def test_unreadable_code_is_a_400(self, as_user, member):
        response = do_import(as_user(member), "WFG1:deadbeef:AAAA")
        assert response.status_code == 400 and "incomplet" in str(response.data["code"])


RETAIL_CLIENT = {"version": "12.1.5", "build": "64567", "toc": 120105, "project": 1}
FOREVER_CLIENT = {"version": "1.15.0", "build": "60000", "toc": 16001, "project": 1}


class TestLevelFromEvents:
    """Filet pour les addons d'avant la 0.4.5 : le niveau exporté ne peut pas être sous la dernière montée."""

    def test_level_is_raised_to_the_last_level_up_event(self):
        raw = {
            "guid": "Player-1-1",
            "name": "Koj",
            "level": 23,
            "exported_at": 1794129488,
            "events": [{"k": "level", "level": 24, "t": 1794128096}, {"k": "boss", "id": 1, "t": 1}],
        }
        assert services.parse_character(raw).level == 24

    def test_bogus_level_events_are_ignored(self):
        raw = {"guid": "Player-1-1", "name": "Koj", "level": 23, "exported_at": 1794129488}
        for events in (
            None,
            "x",
            [{"k": "level", "level": 99}],
            [{"k": "level", "level": True}],
            [{"k": "level"}],
        ):
            assert services.parse_character({**raw, "events": events}).level == 23


class TestGearImport:
    """Le set « En jeu » garde chaque objet porté : celui que l'index ignore est créé d'après le jeu."""

    @pytest.fixture
    def mage(self, member):
        return Character.objects.create(
            owner=member,
            name="Koj",
            player_class=PlayerClass.objects.get(slug="mage"),
            race=Race.objects.get(slug="human"),
            level=31,
        )

    def worn(self, character):
        current = character.equipment_sets.get(name=services.IN_GAME)
        return {slot.slot: slot.item for slot in current.slots.select_related("item")}

    def test_items_unknown_to_the_index_are_created_from_what_the_game_says(self, mage):
        Item.objects.create(id=253957, name="Diadème nacré", quality=3, inventory_type=1, icon="inv_crown")
        gear = {
            # Connu de l'index : la fiche de l'index fait foi, pas ce que dit l'addon.
            "head": {"id": 253957, "name": "Autre nom", "q": 1},
            # Suffixe aléatoire, sans fiche dans la table du client : créé avec ce que le jeu en sait.
            "legs": {
                "id": 2970,
                "name": "Pantalon  de lieur de sort",
                "q": 2,
                "ilvl": 31,
                "req": 26,
                "inv": 7,
                "cls": 4,
                "sub": 1,
            },
            # Type d'emplacement absent ou incohérent : celui de l'emplacement porté.
            "mainhand": {"id": 273024, "name": "Bâton inédit", "inv": 99},
            # Ancien addon (ni nom ni qualité) ou valeurs aberrantes : l'emplacement reste vide.
            "feet": {"id": 6570},
            "waist": {"id": 9793, "name": "   "},
        }
        services._apply_gear(mage, gear)
        worn = self.worn(mage)
        assert set(worn) == {"head", "legs", "main_hand"}
        assert (worn["head"].name, worn["head"].quality, worn["head"].icon) == (
            "Diadème nacré",
            3,
            "inv_crown",
        )
        legs = worn["legs"]
        assert (legs.name, legs.quality, legs.item_level, legs.required_level) == (
            "Pantalon de lieur de sort",
            2,
            31,
            26,
        )
        assert (legs.inventory_type, legs.class_id, legs.subclass_id, legs.is_forever) == (7, 4, 1, False)
        staff = worn["main_hand"]
        assert (staff.quality, staff.item_level, staff.inventory_type) == (1, 1, 13)
        # Rejoué : rien n'est créé en double, la fiche créée n'est pas réécrite.
        services._apply_gear(mage, {"legs": {"id": 2970, "name": "Renommé", "q": 4}})
        assert Item.objects.get(pk=2970).name == "Pantalon de lieur de sort" and set(self.worn(mage)) == {
            "legs"
        }


class TestTalentsImport:
    """Le build « En jeu » se lit par rangée/colonne (grid), par sort (spells) ou par index (points)."""

    @pytest.fixture
    def shaman(self, member):
        shaman = PlayerClass.objects.get(slug="shaman")
        elemental = TalentTree.objects.create(id=261, player_class=shaman, name="Élémentaire", order=1)
        enhancement = TalentTree.objects.create(id=263, player_class=shaman, name="Amélioration", order=2)
        for talent_id, tree, name, row, column, spells in [
            (1, elemental, "Convection", 0, 1, [16039, 16109, 16110, 16111, 16112]),
            (2, enhancement, "Robustesse", 0, 1, [16258, 16293]),
            (3, enhancement, "Maîtrise des boucliers", 0, 2, [16253, 16298, 16299, 16300, 16301]),
            (4, enhancement, "Frappe-tempête", 6, 1, [17364]),
        ]:
            Talent.objects.create(
                id=talent_id, tree=tree, name=name, row=row, column=column, rank_spells=spells
            )
        return Character.objects.create(
            owner=member, name="Thrall", player_class=shaman, race=Race.objects.get(slug="orc"), level=60
        )

    def points(self, character):
        return TalentBuild.objects.get(character=character, name=services.IN_GAME).points

    def test_a_talent_known_by_one_spell_takes_the_rank_the_game_gives(self, shaman):
        # Talent Forever : l'index ne connaît que le sort du rang 1, répété pour chaque rang.
        tree = TalentTree.objects.get(pk=263)
        Talent.objects.create(id=9, tree=tree, name="Nouveau", row=0, column=3, rank_spells=[1326079] * 3)
        services._apply_talents(shaman, {"api": "traits", "spells": {"1326079": 2}})
        assert self.points(shaman) == [9, 9]

    def test_grid_keys_are_one_based_rows_and_columns_per_tree(self, shaman):
        grid = {"1-1-2": 5, "2-1-3": 4, "2-7-2": 1, "9-9-9": 3}
        services._apply_talents(shaman, {"api": "classic", "grid": grid, "points": {"1-1": 1}})
        assert self.points(shaman) == [1] * 5 + [3] * 4 + [4]
        shaman.refresh_from_db()
        assert shaman.specialization.slug == "shaman-enhancement"

    def test_spells_name_the_talent_and_its_rank(self, shaman):
        # Rang 1 du nœud avec le sort du rang 3, un nœud à 2 rangs sur le sort du rang 1, un inconnu, un rang
        # trop haut (borné au rang max).
        spells = {"16299": 1, "16258": 2, "99999": 5, "17364": 9}
        services._apply_talents(shaman, {"api": "traits", "spells": spells})
        assert self.points(shaman) == [2, 2, 3, 3, 3, 4]

    def test_legacy_points_are_still_read_and_unreadable_payloads_change_nothing(self, shaman):
        services._apply_talents(shaman, {"points": {"2-1": 2}})
        assert self.points(shaman) == [2, 2]
        services._apply_talents(shaman, {"api": "traits"})  # aucune lecture : le build reste
        assert self.points(shaman) == [2, 2]
        services._apply_talents(shaman, {"api": "traits", "spells": {}})  # lu, zéro point : build vidé
        assert self.points(shaman) == []


class TestForeignClient:
    def test_other_client_is_refused_without_touching_characters(self, as_user, member):
        response = do_import(as_user(member), export_code(character_payload(), client=RETAIL_CLIENT))
        assert response.status_code == 201, response.data
        (line,) = response.data["snapshots"]
        assert line["status"] == "refused"
        assert line["note"] == (
            "Export d'un autre client (12.1.5, interface 120105) : seul WoW Forever est accepté."
        )
        assert response.data["summary"]["refused"] == 1 and response.data["summary"]["created"] == 0
        assert not Character.objects.filter(guid="Player-1-000ABC01").exists()
        assert ImportBatch.objects.get().client == "12.1.5 (120105)"
        assert CharacterSnapshot.objects.get().name == "Thrall"

    def test_forever_client_is_imported(self, as_user, member):
        response = do_import(as_user(member), export_code(character_payload(), client=FOREVER_CLIENT))
        assert response.status_code == 201, response.data
        assert response.data["summary"]["created"] == 1
        assert ImportBatch.objects.get().client == "1.15.0 (16001)"

    def test_old_addon_without_client_block_is_imported(self, as_user, member):
        response = do_import(as_user(member), export_code(character_payload()))
        assert response.status_code == 201, response.data
        assert response.data["summary"]["created"] == 1
        assert ImportBatch.objects.get().client == ""

    def test_empty_setting_accepts_everything(self, as_user, member):
        settings = GuildSettings.load()
        settings.accepted_interface_versions = ""
        settings.save()
        response = do_import(as_user(member), export_code(character_payload(), client=RETAIL_CLIENT))
        assert response.status_code == 201, response.data
        assert response.data["summary"]["created"] == 1


class TestRelease:
    def test_release_from_github_with_cache(self, as_user, member):
        import httpx
        import respx
        from django.core.cache import cache

        cache.clear()
        with respx.mock:
            route = respx.get("https://api.github.com/repos/Jordan-BDS/wow-forever/releases").mock(
                return_value=httpx.Response(200, json=[
                    {"tag_name": "v1.2.0", "draft": False, "prerelease": False, "assets": []},
                    {"tag_name": "companion-v0.3.1", "draft": False, "prerelease": False, "html_url": "https://github.com/x",
                     "published_at": "2026-12-01T10:00:00Z", "assets": [
                         {"name": "WoWForeverGuilde_0.3.1_x64_en-US.msi", "browser_download_url": "https://dl/x.msi"},
                         {"name": "WoWForeverGuilde_0.3.1_x64-setup.exe", "browser_download_url": "https://dl/x.exe"},
                         {"name": "WoWForeverGuilde_0.3.1_x64_en-US.msi.sig", "browser_download_url": "https://dl/x.msi.sig"},
                         {"name": "WoWForeverGuilde_0.3.1.dmg", "browser_download_url": "https://dl/x.dmg"},
                         {"name": "WoWForeverGuilde-addon-0.3.1.zip", "browser_download_url": "https://dl/addon.zip"},
                     ]},
                ]),
            )  # fmt: skip
            first = as_user(member).get("/api/sync/release/")
            second = as_user(member).get("/api/sync/release/")
        assert first.status_code == 200 and first.data["version"] == "0.3.1"
        assert first.data["assets"] == {
            "windows": "https://dl/x.exe",
            "macos": "https://dl/x.dmg",
            "addon": "https://dl/addon.zip",
        }
        assert second.status_code == 200 and route.call_count == 1  # cache

    def test_no_release_is_204(self, as_user, member):
        import httpx
        import respx
        from django.core.cache import cache

        cache.clear()
        with respx.mock:
            respx.get("https://api.github.com/repos/Jordan-BDS/wow-forever/releases").mock(
                return_value=httpx.Response(404)
            )
            assert as_user(member).get("/api/sync/release/").status_code == 204


class TestAddonErrors:
    def test_errors_are_kept_deduplicated_and_visible_to_gm_only(self, as_user, member, gm):
        seed()
        errors = [
            {
                "t": int(NOW.timestamp()) - 60,
                "where": "pve.onEvent",
                "error": "PvE.lua:63: attempt to index nil",
                "addon": "0.3.1",
            },
            {"t": 0, "where": "", "error": "x" * 3000},
            "pas un dict",
        ]
        first = do_import(as_user(member), export_code(character_payload(), errors=errors))
        assert first.status_code == 201
        batch = ImportBatch.objects.get(pk=first.data["id"])
        assert batch.errors[0]["where"] == "pve.onEvent" and batch.errors[1]["t"] is None
        assert len(batch.errors) == 2 and len(batch.errors[1]["error"]) == 2000
        # Second export : les mêmes erreurs reviennent, une seule fois dans la liste du GM.
        do_import(as_user(member), export_code(character_payload(level=59), errors=errors[:1]))
        assert as_user(member).get("/api/sync/addon-errors/").status_code == 403
        data = as_user(gm).get("/api/sync/addon-errors/").data["errors"]
        # Sans horodatage, l'erreur est datée de la réception (maintenant), donc avant celle datée de NOW.
        assert [(e["where"], e["user"]["display_name"], e["addon"]) for e in data] == [
            ("", member.display_name, "0.1.0"),
            ("pve.onEvent", member.display_name, "0.3.1"),
        ]
        assert data[0]["at"] is None and data[1]["at"].startswith(NOW.strftime("%Y-%m-%d"))


class TestLatestRelease:
    def test_incomplete_release_falls_back_to_previous_and_caches_briefly(self, monkeypatch):
        import httpx
        from django.core.cache import cache

        def asset(name):
            return {"name": name, "browser_download_url": f"https://x/{name}"}

        complete = ["x64-setup.exe", "x64_en-US.msi", "universal.dmg"]
        payload = [
            {
                "tag_name": "companion-v0.3.3",
                "assets": [asset("WoW_0.3.3_universal.dmg"), asset("latest.json")],
            },
            {
                "tag_name": "companion-v0.3.2",
                "assets": [asset(f"WoW_0.3.2_{n}") for n in complete]
                + [asset("WoWForeverGuilde-addon-0.3.2.zip")],
            },
        ]

        class Response:
            status_code = 200

            def json(self):
                return payload

        set_calls = []
        monkeypatch.setattr(httpx, "get", lambda *a, **k: Response())
        monkeypatch.setattr(cache, "set", lambda key, value, ttl: set_calls.append((value, ttl)))
        release = services.latest_release(force=True)
        assert release["version"] == "0.3.2" and release["assets"]["windows"].endswith("setup.exe")
        assert set_calls[-1][1] == 60  # on revérifie dans la minute
        # Une fois les fichiers tous là, la 0.3.3 passe et le cache redevient long.
        payload[0]["assets"] += [asset("WoW_0.3.3_x64-setup.exe"), asset("WoWForeverGuilde-addon-0.3.3.zip")]
        release = services.latest_release(force=True)
        assert release["version"] == "0.3.3" and set_calls[-1][1] == 3600
