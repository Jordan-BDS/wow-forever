# ruff: noqa: E501 — les charges utiles JSON des scénarios sont longues par nature
"""Fiche vivante et classements : deltas par période, agrégation par joueur, titres du lundi, progression."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from apps.characters.models import Character
from apps.gamedata.models import Item, PlayerClass, Race
from apps.gamedata.seed import seed
from apps.notifications.models import Notification

from . import rankings, services, titles
from .format import encode_export
from .models import WeeklyTitle

pytestmark = pytest.mark.django_db

PARIS = ZoneInfo("Europe/Paris")
# Lundi 21 décembre 2026, 20h à Paris : la semaine en cours a commencé ce matin.
NOW = datetime(2026, 12, 21, 20, 0, tzinfo=PARIS)
EXPORTED = int(datetime(2026, 12, 21, 19, 0, tzinfo=PARIS).timestamp())
KILL_TIME = int(datetime(2026, 12, 20, 21, 30, tzinfo=PARIS).timestamp())


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
            "deaths": 14, "boss_kills": 3, "gathering": {"mining": 310}, "bg_played": 12, "bg_won": 9, "quests": 50, "hk": 100,
            "bosses": {"672": {"n": 1, "name": "Ragnaros", "first": KILL_TIME, "last": KILL_TIME}},
        },
        journal={
            "2026-12-13": {"deaths": 2, "gathering": {"mining": 20}, "bg_played": 0, "bg_won": 0, "hk": 10},
            "2026-12-20": {"deaths": 10, "boss_kills": 3, "gathering": {"mining": 100}, "bg_played": 10, "bg_won": 8, "hk": 60},
        },
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
        counters={"deaths": 30, "gathering": {"mining": 50}},
        journal={"2026-12-20": {"deaths": 25, "gathering": {"mining": 50}}},
        events=[{"k": "boss", "id": 672, "name": "Ragnaros", "t": KILL_TIME + 60, "guild": 6}],
    )  # fmt: skip


def import_for(user, *chars):
    return services.import_code(user, encode_export({"v": 1, "characters": list(chars)}), source="paste")


class TestRankings:
    def test_week_deltas_by_player_and_character(self, member, other_member):
        import_for(
            member,
            thrall(),
            character("Player-1-A", "Alt", counters={"deaths": 1}, journal={"2026-12-20": {"deaths": 0}}),
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
        # Mois : pas de valeur connue avant le 1er décembre → base = plus ancienne connue (13/12), marquée
        month = rankings.compute_rankings("month", "player", now=NOW)
        deaths_m = {c["key"]: c for c in month["categories"]}["deaths"]["entries"][0]
        assert deaths_m["value"] == 12.0 and deaths_m["since"] == "2026-12-13"

    def test_guild_progression_dedupes_group_kills(self, member, other_member):
        import_for(member, thrall())
        import_for(other_member, garona())
        (molten,) = rankings.compute_rankings("week", "player", now=NOW)["progression"]
        assert (molten["slug"], molten["killed"], molten["total"]) == ("molten-core", 1, 10)
        bosses = {b["name"]: b for b in molten["bosses"]}
        assert bosses["Ragnaros"]["kills"] == 1 and bosses["Ragnaros"]["first_kill"].startswith(
            "2026-12-20T20:30"
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
        early = datetime(2026, 12, 21, 9, 59, tzinfo=PARIS)
        assert titles.award_weekly_titles(early) == []
        created = titles.award_weekly_titles(datetime(2026, 12, 21, 10, 0, tzinfo=PARIS))
        by_key = {t.key: t for t in created}
        assert (
            by_key["gathering"].user == member and by_key["gathering"].value == 80.0
        )  # 100 − 20 sur la semaine close
        assert (
            by_key["shame"].user == member and by_key["shame"].value == 8.0
        )  # Garona : pas de valeur avant le 20
        assert by_key["boss"].user == member and by_key["boss"].value == 3.0
        assert by_key["bg"].value == 50.0  # 60 − 10 joueurs tués sur la semaine close
        recap = Notification.objects.get(kind="weekly_recap")
        assert (
            "Mineur de la semaine" in recap.text
            and member.display_name in recap.text
            and "80 minerais" in recap.text
        )
        assert titles.award_weekly_titles(NOW) == [] and WeeklyTitle.objects.count() == len(created)
        shown = rankings.current_titles(NOW)
        assert {t["key"] for t in shown} == set(by_key) and shown[0]["week_start"] == "2026-12-14"

    def test_scan_reminders_calls_the_award(self, member):
        from apps.notifications.reminders import scan_due_reminders

        import_for(member, thrall())
        scan_due_reminders(datetime(2026, 12, 21, 11, 0, tzinfo=PARIS))
        assert WeeklyTitle.objects.filter(week_start="2026-12-14").exists()


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
        assert data["bosses"][0]["first"].startswith("2026-12-20T20:30")
        gear = {g["slot"]: g for g in data["gear"]}
        assert gear["head"]["name"] == "Couronne de la Terre" and gear["head"]["enchant_id"] == 2583
        assert gear["mainhand"]["name"] is None  # objet absent de l'index : identifiant seul
        assert data["pvp"]["battlegrounds"] == [{"map": "Goulet", "played": 12, "won": 9}]
        assert [s["day"] for s in data["series"]] == ["2026-12-13", "2026-12-20"]
        assert data["levels"][0]["level"] == 60 and len(data["syncs"]) == 1

    def test_never_synced_character(self, as_user, member):
        plain = Character.objects.create(
            owner=member, name="Manuel", player_class=PlayerClass.objects.get(slug="mage"),
            race=Race.objects.get(slug="undead"), level=20, main_role="dps",
        )  # fmt: skip
        response = as_user(member).get(f"/api/sync/characters/{plain.pk}/progress/")
        assert response.status_code == 200 and response.data == {"available": False}
