# ruff: noqa: E501 — les charges utiles JSON des scénarios sont longues par nature
"""Fiche vivante et classements : deltas par période, agrégation par joueur, titres du lundi, progression."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from apps.characters.models import Character
from apps.gamedata.models import Item, PlayerClass, Race
from apps.gamedata.seed import seed
from apps.notifications.models import Notification

from . import progress, rankings, services, titles
from .format import encode_export
from .models import WeeklyTitle

pytestmark = pytest.mark.django_db

PARIS = ZoneInfo("Europe/Paris")
# Lundi 21 septembre 2026, 20h à Paris : la semaine en cours a commencé ce matin. Dates passées : un export
# daté dans le futur est ramené à maintenant à l'import.
NOW = datetime(2026, 9, 21, 20, 0, tzinfo=PARIS)
EXPORTED = int(datetime(2026, 9, 21, 19, 0, tzinfo=PARIS).timestamp())
KILL_TIME = int(datetime(2026, 9, 20, 21, 30, tzinfo=PARIS).timestamp())


@pytest.fixture(autouse=True)
def gamedata(db):
    seed()
    Item.objects.create(id=16842, name="Couronne de la Terre", quality=4, item_level=66)


def character(guid, name, *, counters, journal, events=(), **extra):
    return {
        "guid": guid, "name": name, "surname": "Test", "realm": "Forever", "class": "SHAMAN", "race": "Orc",
        "level": 60, "exported_at": EXPORTED, "counting_since": EXPORTED - 30 * 86400,
        "counters": counters, "journal": journal, "events": list(events), **extra,
    }  # fmt: skip


def thrall():
    return character(
        "Player-1-T", "Thrall",
        counters={
            "deaths": 14, "boss_kills": 3, "gathering": {"mining": 310}, "bg_played": 12, "bg_won": 9, "quests": 50, "hk": 100, "kills": 120, "mobs": {"299": 70, "6": 50},
            "bosses": {"672": {"n": 1, "name": "Ragnaros", "first": KILL_TIME, "last": KILL_TIME}},
        },
        journal={
            "2026-09-13": {"deaths": 2, "gathering": {"mining": 20}, "bg_played": 0, "bg_won": 0, "hk": 10, "quests": 10},
            "2026-09-20": {"deaths": 10, "boss_kills": 3, "gathering": {"mining": 100, "fishing": 7}, "bg_played": 10, "bg_won": 8, "hk": 60, "kills": 100, "quests": 30, "crafted_total": 5, "mobs": {"299": 60, "6": 50}},
        },
        mobs={"299": {"n": 70, "name": "Loup des Tarides", "first": KILL_TIME - 86400, "last": KILL_TIME}, "6": {"n": 50, "name": "Kobold"}},
        events=[
            {"k": "boss", "id": 672, "name": "Ragnaros", "t": KILL_TIME, "guild": 6},
            {"k": "boss", "id": 663, "name": "Lucifron", "t": KILL_TIME - 3600, "guild": 2},
            {"k": "level", "t": KILL_TIME - 86400 * 3, "level": 60},
        ],
        gear={"head": {"id": 16842, "ench": 2583}, "mainhand": {"id": 999999}},
        reputations={"609": {"v": 9800, "r": 6, "n": "Cercle cénarien"}},
        attunements={"molten-core": True, "onyxia": False},
        lockouts=[{"name": "Cœur du Magma", "reset_at": EXPORTED + 86400 * 3, "raid": True, "bosses": 10, "killed": 7}],
        pvp={"hk_lifetime": 2340, "rank": 8, "bg": {"Goulet": {"played": 12, "won": 9}}},
    )  # fmt: skip


def garona():
    return character(
        "Player-1-G", "Garona",
        counters={"deaths": 30, "gathering": {"mining": 50}, "kills": 90, "mobs": {"299": 90, "0": 3, "7": 0}},
        journal={"2026-09-20": {"deaths": 25, "gathering": {"mining": 50}, "kills": 10, "mobs": {"299": 40}}},
        mobs={"299": {"n": 90, "name": "Loup", "last": KILL_TIME + 60}, "0": {"n": 3}, "7": {"n": 0}},
        events=[{"k": "boss", "id": 672, "name": "Ragnaros", "t": KILL_TIME + 60, "guild": 6}],
    )  # fmt: skip


def import_for(user, *chars, install="pc-fixe"):
    payload = {"v": 1, "install": install, "characters": list(chars)}
    return services.import_code(user, encode_export(payload), source="paste")


class TestInstalls:
    """Deux installations de l'addon (second PC, réinstallation) : chacune compte depuis zéro, le site additionne
    au lieu d'oublier l'ancienne."""

    def test_counters_journal_and_state_are_merged_across_installs(self, member):
        import_for(member, thrall(), install="pc-fixe")
        fresh = character(
            "Player-1-T", "Thrall",
            counters={"deaths": 2, "kills": 5, "hk": 100, "gathering": {"mining": 15}, "mobs": {"299": 5}},
            journal={},
            mobs={"299": {"n": 5, "name": "Loup des Tarides", "first": EXPORTED + 60, "last": EXPORTED + 500}},
            events=[{"k": "death", "t": EXPORTED + 300, "zone": "Durotar"}],
            gear={"head": {"id": 16842}},
            pvp={"hk_lifetime": 100, "rank": 8, "bg": {"Goulet": {"played": 1, "won": 1}}},
        )  # fmt: skip
        fresh["exported_at"] = EXPORTED + 600
        fresh["counting_since"] = EXPORTED  # réinstallé aujourd'hui : compteurs repartis de zéro
        import_for(member, fresh, install="portable")
        thrall_char = Character.objects.get(name="Thrall")
        # Les deux instantanés du jour sont conservés, un par installation.
        assert thrall_char.snapshots.filter(status__in=progress.APPLIED).count() == 2
        merged = progress.latest_snapshot(thrall_char)
        assert merged.installs == 2 and merged.data["counting_since"] == EXPORTED - 30 * 86400
        c = merged.data["counters"]
        assert (c["deaths"], c["kills"], c["gathering"]["mining"], c["mobs"]["299"]) == (16, 125, 325, 75)
        assert (
            c["hk"] == 100 and merged.data["pvp"]["hk_lifetime"] == 2340
        )  # totaux du jeu : jamais additionnés
        assert merged.data["pvp"]["bg"]["Goulet"] == {"played": 13, "won": 10}
        assert merged.data["mobs"]["299"] == {
            "n": 75, "name": "Loup des Tarides", "first": KILL_TIME - 86400, "last": EXPORTED + 500
        }  # fmt: skip
        assert [e["k"] for e in merged.data["events"]][-1] == "death"
        # Journal : les jours de l'ancienne installation, sans contribution de la nouvelle qui n'existait pas.
        assert (
            merged.data["journal"]["2026-09-20"]["deaths"] == 10
            and merged.data["journal"]["2026-09-20"]["hk"] == 60
        )
        assert merged.data["gear"] == {"head": {"id": 16842}}  # état : export le plus récent
        data = progress.character_progress(thrall_char, now=NOW)
        assert data["tiles"]["deaths"] == {"total": 16.0, "week": 14.0}  # 16 − 2 (journal du 13)
        assert data["tiles"]["hk"] == {"total": 100.0, "week": 90.0}
        assert data["gathering_week"]["mining"] == 305.0
        assert data["gear"][0]["enchant_id"] is None
        result = rankings.compute_rankings("week", "character", now=NOW)
        by_key = {cat["key"]: cat for cat in result["categories"]}
        assert [(e["character"]["name"], e["value"]) for e in by_key["deaths"]["entries"]] == [
            ("Thrall", 6.0)
        ]
        assert [(e["value"]) for e in by_key["mining"]["entries"]] == [225.0]  # 325 − 100
        assert [(e["value"]) for e in by_key["hk"]["entries"]] == [40.0]  # 100 − 60, pas 100 + 100
        assert result["characters"] == 1
        # Retour sur l'ancien PC : son nouvel export remplace le sien, l'autre installation reste comptée.
        back = thrall()
        back["counters"]["deaths"] = 15
        back["exported_at"] = EXPORTED + 1200
        import_for(member, back, install="pc-fixe")
        merged = progress.latest_snapshot(thrall_char)
        assert merged.data["counters"]["deaths"] == 17
        assert merged.data["gear"]["head"] == {"id": 16842, "ench": 2583}
        assert thrall_char.snapshots.filter(status__in=progress.APPLIED).count() == 2
        assert merged.bases == {"pc-fixe": EXPORTED + 1200, "portable": EXPORTED + 600}

    def test_a_seeded_install_counts_the_others_only_after_their_base(self, member):
        # Le compagnon du portable a recopié l'état du site (fixe compris jusqu'à son export EXPORTED) :
        # l'export suivant du portable porte la marque, et le fixe ne compte que ce qu'il fait depuis.
        import_for(member, thrall(), install="pc-fixe")
        thrall_char = Character.objects.get(name="Thrall")
        state = progress.companion_state(member)
        (served,) = state["characters"]
        assert served["guid"] == "Player-1-T" and served["counters"]["deaths"] == 14
        assert served["bases"] == {"pc-fixe": EXPORTED} and state["seed_at"] > EXPORTED
        assert thrall_char.snapshots.get().kept is True
        seeded = character(
            "Player-1-T", "Thrall",
            counters={**served["counters"], "deaths": 16},  # deux morts de plus sur le portable
            journal=served["journal"],
            mobs=served["mobs"], events=served["events"], pvp=served["pvp"],
            seed={"at": state["seed_at"], "bases": served["bases"]},
        )  # fmt: skip
        seeded["exported_at"] = EXPORTED + 600
        import_for(member, seeded, install="portable")
        merged = progress.latest_snapshot(thrall_char)
        assert merged.installs == 2 and merged.data["counters"]["deaths"] == 16  # pas 14 + 16
        assert merged.data["counters"]["kills"] == 120 and merged.data["mobs"]["299"]["n"] == 70
        assert merged.data["journal"]["2026-09-20"]["deaths"] == 10
        # Le fixe rejoue après la base : seule la différence depuis son export EXPORTED s'ajoute.
        back = thrall()
        back["counters"]["deaths"] = 20
        back["counters"]["kills"] = 130
        back["mobs"]["299"]["n"] = 80
        back["events"].append({"k": "death", "t": EXPORTED + 1500, "zone": "Durotar"})
        back["exported_at"] = EXPORTED + 1800
        import_for(member, back, install="pc-fixe")
        merged = progress.latest_snapshot(thrall_char)
        c = merged.data["counters"]
        assert (c["deaths"], c["kills"], c["hk"]) == (16 + 6, 120 + 10, 100)
        assert (
            merged.data["mobs"]["299"]["n"] == 80 and merged.data["mobs"]["299"]["first"] == KILL_TIME - 86400
        )
        assert [e for e in merged.data["events"] if e["k"] == "death"] == [
            {"k": "death", "t": EXPORTED + 1500, "zone": "Durotar"}
        ]
        # Le nettoyage du jour a gardé la base (instantané conservé) à côté du nouvel export du fixe.
        assert thrall_char.snapshots.filter(status__in=progress.APPLIED).count() == 3
        assert merged.bases == {"pc-fixe": EXPORTED + 1800, "portable": EXPORTED + 600}
        result = rankings.compute_rankings("week", "character", now=NOW)
        by_key = {cat["key"]: cat for cat in result["categories"]}
        assert [e["value"] for e in by_key["deaths"]["entries"]] == [12.0]  # 22 − 10


class TestRankings:
    def test_week_deltas_by_player_and_character(self, member, other_member):
        import_for(
            member,
            thrall(),
            character("Player-1-A", "Alt", counters={"deaths": 1}, journal={"2026-09-20": {"deaths": 0}}),
        )
        import_for(other_member, garona())
        result = rankings.compute_rankings("week", "player", now=NOW)
        by_key = {c["key"]: c for c in result["categories"]}
        deaths = by_key["deaths"]["entries"]
        # Garona : 30 − 25 = 5 ; Thrall + Alt : (14 − 10) + (1 − 0) = 5 → ex æquo, ordre alphabétique des joueurs
        assert [(e["user"]["display_name"], e["value"], e["rank"]) for e in deaths] == [
            (member.display_name, 5.0, 1),
            (other_member.display_name, 5.0, 1),
        ] or [(e["value"], e["rank"]) for e in deaths] == [(5.0, 1), (5.0, 1)]
        mining = by_key["mining"]["entries"]
        assert mining[0]["user"]["id"] == member.pk and mining[0]["value"] == 210.0
        assert mining[0]["previous_rank"] == 1  # semaine précédente : 100 − 20 = 80
        assert mining[0]["character"]["name"] == "Thrall"
        assert len(mining) == 1  # Garona : 0 cette semaine, absente
        assert by_key["bg_rate"]["entries"][0]["value"] == 50.0  # 1 gagné sur 2 cette semaine
        assert result["players"] == 2 and result["characters"] == 3

        per_character = rankings.compute_rankings("week", "character", now=NOW)
        deaths_c = {c["key"]: c for c in per_character["categories"]}["deaths"]["entries"]
        assert [(e["character"]["name"], e["value"]) for e in deaths_c] == [
            ("Garona", 5.0),
            ("Thrall", 4.0),
            ("Alt", 1.0),
        ]

    def test_all_time_and_since_marker(self, member):
        import_for(member, thrall())
        total = rankings.compute_rankings("all", "player", now=NOW)
        deaths = {c["key"]: c for c in total["categories"]}["deaths"]["entries"][0]
        assert deaths["value"] == 14.0 and deaths["previous_rank"] is None
        # Mois : pas de valeur connue avant le 1er septembre → base = plus ancienne connue (13/09), marquée
        month = rankings.compute_rankings("month", "player", now=NOW)
        deaths_m = {c["key"]: c for c in month["categories"]}["deaths"]["entries"][0]
        assert deaths_m["value"] == 12.0 and deaths_m["since"] == "2026-09-13"

    def test_first_week_counts_from_counting_since(self, member):
        # Addon installé mardi 22/09 (compteurs à zéro), seule entrée du journal mardi soir (3 boss), 5 boss
        # au total jeudi : la semaine doit donner 5, pas 5 − 3.
        thursday = datetime(2026, 9, 24, 20, 0, tzinfo=PARIS)
        tuesday = int(datetime(2026, 9, 22, 10, 0, tzinfo=PARIS).timestamp())
        import_for(
            member,
            character(
                "Player-1-N",
                "Nouveau",
                counters={"boss_kills": 5},
                journal={"2026-09-22": {"boss_kills": 3}},
                exported_at=int(datetime(2026, 9, 24, 19, 0, tzinfo=PARIS).timestamp()),
                counting_since=tuesday,
            ),  # fmt: skip
        )
        week = rankings.compute_rankings("week", "character", now=thursday)
        (entry,) = {c["key"]: c for c in week["categories"]}["boss_kills"]["entries"]
        assert entry["value"] == 5.0 and entry["since"] == "2026-09-22"
        # Même chose pour la tuile « cette semaine » de la fiche
        tiles = progress.character_progress(Character.objects.get(guid="Player-1-N"), now=thursday)
        assert tiles["tiles"]["boss_kills"] == {"total": 5.0, "week": 5.0}

    def test_kills_category_and_guild_hunting_board(self, member, other_member):
        import_for(member, thrall())
        import_for(other_member, garona())
        result = rankings.compute_rankings("week", "player", now=NOW)
        kills = {c["key"]: c for c in result["categories"]}["kills"]
        assert kills["group"] == "pve" and [(e["user"]["id"], e["value"]) for e in kills["entries"]] == [
            (other_member.pk, 80.0),
            (member.pk, 20.0),
        ]
        assert result["week_totals"]["kills"] == 100.0
        # Tableau de chasse de la semaine : différence du journal par espèce (Thrall 70 − 60, Garona 90 − 40 ;
        # « 0 » sans valeur avant → 3), nombre de chasseurs, meilleur chasseur ; les espèces sans kill sortent.
        board = result["mobs"]
        assert [(m["id"], m["name"], m["kills"], m["hunters"]) for m in board] == [
            (299, "Loup des Tarides", 60, 2),
            (0, "Créature 0", 3, 1),
        ]
        assert board[0]["top"]["user"]["id"] == other_member.pk and board[0]["top"]["kills"] == 50
        assert board[0]["top"]["character"]["name"] == "Garona"
        assert board[0]["last_kill"].startswith("2026-09-20T19:31")
        assert board[1]["last_kill"] is None
        assert result["mob_of_week"]["current"]["kills"] == 60
        # Semaine close (14-20/09) : Thrall 60 − 0 (rien avant le 13) ; Garona : plus ancienne valeur le 20 → 0.
        previous = result["mob_of_week"]["previous"]
        assert (previous["id"], previous["kills"], previous["hunters"]) == (299, 60, 1)
        # Total depuis l'installation : le nom vient du premier export qui en a un.
        total = rankings.compute_rankings("all", "player", now=NOW)["mobs"]
        assert [(m["id"], m["name"], m["kills"], m["hunters"]) for m in total] == [
            (299, "Loup des Tarides", 160, 2),
            (6, "Kobold", 50, 1),
            (0, "Créature 0", 3, 1),
        ]
        assert total[0]["top"]["kills"] == 90

    def test_guild_progression_dedupes_group_kills(self, member, other_member):
        import_for(member, thrall())
        import_for(other_member, garona())
        (molten,) = rankings.compute_rankings("week", "player", now=NOW)["progression"]
        assert (molten["slug"], molten["killed"], molten["total"]) == ("molten-core", 1, 10)
        bosses = {b["name"]: b for b in molten["bosses"]}
        assert bosses["Ragnaros"]["kills"] == 1 and bosses["Ragnaros"]["first_kill"].startswith(
            "2026-09-20T19:30"
        )
        assert (
            bosses["Lucifron"]["kills"] == 0 and bosses["Lucifron"]["best_group"] == 2
        )  # moins de 5 guildiens
        assert len(molten["bosses"]) == 10 and molten["first_clear"] is None

    def test_rankings_endpoint_and_cache(self, as_user, member):
        import_for(member, thrall())
        response = as_user(member).get("/api/sync/rankings/", {"period": "week", "by": "character"})
        assert response.status_code == 200 and response.data["by"] == "character"
        assert response.data["levels"][-1] == {"label": "60", "count": 1}
        assert as_user(member).get("/api/sync/rankings/", {"period": "bidon"}).data["period"] == "week"


class TestTitles:
    def test_awarded_monday_after_ten_then_frozen(self, member, other_member):
        import_for(member, thrall())
        import_for(other_member, garona())
        early = datetime(2026, 9, 21, 9, 59, tzinfo=PARIS)
        assert titles.award_weekly_titles(early) == []
        created = titles.award_weekly_titles(datetime(2026, 9, 21, 10, 0, tzinfo=PARIS))
        by_key = {t.key: t for t in created}
        assert (
            by_key["gathering"].user == member and by_key["gathering"].value == 87.0
        )  # 100 − 20 minerais + 7 poissons sur la semaine close
        assert (
            by_key["shame"].user == member and by_key["shame"].value == 8.0
        )  # Garona : pas de valeur avant le 20
        assert by_key["boss"].user == member and by_key["boss"].value == 3.0
        assert (
            by_key["kills"].user == member and by_key["kills"].value == 100.0
        )  # Garona : 10 sur la semaine close
        assert by_key["bg"].value == 50.0  # 60 − 10 joueurs tués sur la semaine close
        assert by_key["crafting"].value == 5.0 and by_key["fishing"].value == 7.0
        assert by_key["quests"].user == member and by_key["quests"].value == 20.0  # 30 − 10
        recap = Notification.objects.get(kind="weekly_recap")
        assert (
            "Farmeur chinois" in recap.text
            and member.display_name in recap.text
            and "87 ressources" in recap.text
        )
        assert (
            "Nat Pagle" in recap.text and "7 poissons" in recap.text and "20 quêtes" in recap.text
        )
        assert titles.award_weekly_titles(NOW) == [] and WeeklyTitle.objects.count() == len(created)
        shown = rankings.current_titles(NOW)
        assert {t["key"] for t in shown} == set(by_key) and shown[0]["week_start"] == "2026-09-14"

    def test_scan_reminders_calls_the_award(self, member):
        from apps.notifications.reminders import scan_due_reminders

        import_for(member, thrall())
        scan_due_reminders(datetime(2026, 9, 21, 11, 0, tzinfo=PARIS))
        assert WeeklyTitle.objects.filter(week_start="2026-09-14").exists()


class TestProgress:
    def test_character_progress_endpoint(self, as_user, member):
        import_for(member, thrall())
        thrall_db = Character.objects.get(guid="Player-1-T")
        response = as_user(member).get(f"/api/sync/characters/{thrall_db.pk}/progress/")
        data = response.data
        assert response.status_code == 200 and data["available"] is True
        assert data["tiles"]["deaths"]["total"] == 14.0
        assert data["gathering"] == {"mining": 310, "herbalism": 0, "skinning": 0, "fishing": 0}
        assert data["attunements"] == {"molten-core": True, "onyxia": False}
        assert data["lockouts"][0]["killed"] == 7 and data["lockouts"][0]["reset_at"]
        assert data["reputations"][0]["name"] == "Cercle cénarien"
        assert [(b["id"], b["name"], b["kills"]) for b in data["bosses"]] == [(672, "Ragnaros", 1)]
        assert data["bosses"][0]["first"].startswith("2026-09-20T19:30")
        assert data["tiles"]["kills"]["total"] == 120.0
        assert [(m["id"], m["name"], m["kills"], m["week"]) for m in data["mobs"]] == [
            (299, "Loup des Tarides", 70, 0),  # semaine = les 7 derniers jours réels, pas septembre
            (6, "Kobold", 50, 0),
        ]
        assert data["mobs"][0]["last"].startswith("2026-09-20T19:30") and data["mobs_distinct"] == 2
        gear = {g["slot"]: g for g in data["gear"]}
        assert gear["head"]["name"] == "Couronne de la Terre" and gear["head"]["enchant_id"] == 2583
        assert gear["mainhand"]["name"] is None  # objet absent de l'index : identifiant seul
        assert data["pvp"]["battlegrounds"] == [{"map": "Goulet", "played": 12, "won": 9}]
        assert [s["day"] for s in data["series"]] == ["2026-09-13", "2026-09-20"]
        assert data["levels"][0]["level"] == 60 and len(data["syncs"]) == 1

    def test_never_synced_character(self, as_user, member):
        plain = Character.objects.create(
            owner=member, name="Manuel", player_class=PlayerClass.objects.get(slug="mage"),
            race=Race.objects.get(slug="undead"), level=20, main_role="dps",
        )  # fmt: skip
        response = as_user(member).get(f"/api/sync/characters/{plain.pk}/progress/")
        assert response.status_code == 200 and response.data == {"available": False}
