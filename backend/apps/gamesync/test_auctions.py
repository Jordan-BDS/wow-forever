from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.gamedata.models import Item

from . import auctions, services
from .models import AuctionPrice, AuctionScan

pytestmark = pytest.mark.django_db

HOUSE = "Forever-Alliance"
NOW = timezone.now().replace(microsecond=0)


def stamp(ago: timedelta) -> int:
    return int((NOW - ago).timestamp())


def post_scan(client, items, ago=timedelta(0), house=HOUSE):
    body = {"house": house, "scanned_at": stamp(ago), "items": items}
    return client.post("/api/sync/auctions/", body, format="json")


@pytest.fixture(autouse=True)
def fresh_cache():
    # La comparaison de deux scans est en cache par identifiants, réutilisés d'un test à l'autre.
    cache.clear()


@pytest.fixture
def items(db):
    Item.objects.create(id=2589, name="Étoffe de lin", quality=1, icon="inv_fabric_linen_01")
    Item.objects.create(id=2592, name="Étoffe de laine", quality=1, icon="inv_fabric_wool_01")


def companion_token(user) -> str:
    pairing = services.create_pairing_code(user)
    _, token = services.pair_device(pairing.code, "PC")
    return token


class TestUpload:
    def test_only_the_gm_sends_and_reads(self, api_client, as_user, member, officer):
        for user in (member, officer):
            as_user(user)
            assert post_scan(api_client, [[2589, 100, 3]]).status_code == 403
            assert api_client.get("/api/sync/auctions/").status_code == 403
            assert api_client.get("/api/sync/auctions/items/2589/").status_code == 403
        api_client.force_authenticate(None)
        assert post_scan(api_client, [[2589, 100, 3]]).status_code in (401, 403)
        assert not AuctionScan.objects.exists()

    def test_companion_of_the_gm_sends_a_scan_once(self, api_client, gm):
        api_client.credentials(HTTP_AUTHORIZATION=f"Companion {companion_token(gm)}")
        response = post_scan(api_client, [[2589, 100, 3], [2592, 2500]])
        assert response.status_code == 201
        assert response.json()["items"] == 2
        scan = AuctionScan.objects.get()
        assert (scan.house, scan.user, scan.device.name, scan.scanned_at) == (HOUSE, gm, "PC", NOW)
        assert sorted(scan.prices.values_list("item_id", "price", "listed")) == [
            (2589, 100, 3),
            (2592, 2500, None),
        ]
        # Le même scan renvoyé (autre PC, compagnon réinstallé) ne se compte pas deux fois.
        assert post_scan(api_client, [[2589, 100, 3]]).status_code == 409
        assert AuctionPrice.objects.count() == 2

    def test_companion_of_a_member_is_refused_and_told_so(self, api_client, member, gm):
        api_client.credentials(HTTP_AUTHORIZATION=f"Companion {companion_token(member)}")
        assert api_client.get("/api/sync/auctions/rights/").json() == {"upload": False}
        assert post_scan(api_client, [[2589, 100, 3]]).status_code == 403
        api_client.credentials(HTTP_AUTHORIZATION=f"Companion {companion_token(gm)}")
        assert api_client.get("/api/sync/auctions/rights/").json() == {"upload": True}

    def test_the_right_to_send_has_a_single_rule(self, api_client, as_user, member, monkeypatch):
        # Ouvrir le droit à d'autres se fait dans `can_upload` seulement : le drapeau et les vues suivent.
        monkeypatch.setattr(auctions, "can_upload", lambda user: user == member)
        as_user(member)
        assert api_client.get("/api/sync/auctions/rights/").json() == {"upload": True}
        assert post_scan(api_client, [[2589, 100, 3]]).status_code == 201
        assert api_client.get("/api/sync/auctions/").status_code == 200
        assert api_client.get("/api/sync/auctions/items/2589/").status_code == 200

    def test_old_scans_are_thinned_to_one_per_day(self, gm):
        old = [timedelta(days=40, hours=h) for h in (3, 2, 0)]
        for ago in (*old, timedelta(hours=2), timedelta(0)):
            auctions.store_scan(gm, HOUSE, stamp(ago), [[2589, 100, 3]])
        kept = [NOW - scan.scanned_at for scan in AuctionScan.objects.order_by("scanned_at")]
        # Il y a 40 jours : le dernier scan de chaque jour reste. Les récents sont tous gardés.
        last_of_day = {timezone.localtime(NOW - ago).date(): ago for ago in old}
        assert kept == [*sorted(last_of_day.values(), reverse=True), timedelta(hours=2), timedelta(0)]
        assert len(kept) < 5
        assert AuctionPrice.objects.count() == len(kept)

    @pytest.mark.parametrize(
        "body",
        [
            {"house": "", "scanned_at": 1794342484, "items": [[1, 2, 3]]},
            {"house": HOUSE, "scanned_at": None, "items": [[1, 2, 3]]},
            {"house": HOUSE, "scanned_at": 99999999999, "items": [[1, 2, 3]]},
            {"house": HOUSE, "scanned_at": 1794342484, "items": []},
            {"house": HOUSE, "scanned_at": 1794342484, "items": [[1, 0, 3]]},
            {"house": HOUSE, "scanned_at": 1794342484, "items": [[1, "2", 3]]},
            {"house": HOUSE, "scanned_at": 1794342484, "items": [[1, 2, "3"]]},
            {"house": HOUSE, "scanned_at": 1794342484, "items": [[1, 2, 3.0]]},
            {"house": HOUSE, "scanned_at": 1794342484, "items": [[1]]},
            {"house": HOUSE, "scanned_at": 1794342484, "items": {"1": 2}},
        ],
    )
    def test_unreadable_scans_are_refused_whole(self, api_client, as_user, gm, body):
        as_user(gm)
        assert api_client.post("/api/sync/auctions/", body, format="json").status_code == 400
        assert not AuctionScan.objects.exists()


class TestRead:
    @pytest.fixture
    def scans(self, gm, items):
        auctions.store_scan(gm, HOUSE, stamp(timedelta(days=8)), [[2589, 50, 10], [2592, 400, 2]])
        auctions.store_scan(gm, HOUSE, stamp(timedelta(hours=1)), [[2589, 80, 6], [2592, 500, 4]])
        auctions.store_scan(gm, HOUSE, stamp(timedelta(0)), [[2589, 100, 3], [2592, 250, 9], [99999, 7, 1]])
        auctions.store_scan(gm, "Forever-Horde", stamp(timedelta(days=2)), [[2589, 999, 1]])

    def test_latest_scan_compared_to_the_previous_one(self, api_client, as_user, gm, scans):
        as_user(gm)
        data = api_client.get("/api/sync/auctions/").json()
        assert [(h["house"], h["scans"]) for h in data["houses"]] == [(HOUSE, 3), ("Forever-Horde", 1)]
        assert data["house"] == HOUSE and data["total"] == 3
        rows = {r["item_id"]: r for r in data["results"]}
        assert (rows[2589]["name"], rows[2589]["price"], rows[2589]["previous_price"]) == (
            "Étoffe de lin",
            100,
            80,
        )
        assert rows[2589]["change"] == 25.0 and rows[2592]["change"] == -50.0
        assert rows[2589]["icon_url"].endswith("inv_fabric_linen_01.jpg")
        # Objet absent du scan de référence, et inconnu de l'index : pas de variation, nommé par son ID.
        assert (rows[99999]["name"], rows[99999]["known"], rows[99999]["change"]) == (
            "Objet 99999",
            False,
            None,
        )

    def test_baseline_search_sort_and_house(self, api_client, as_user, gm, scans):
        as_user(gm)
        week = api_client.get("/api/sync/auctions/", {"since": "week", "sort": "up"}).json()
        assert week["baseline"]["items"] == 2
        assert [(r["item_id"], r["change"]) for r in week["results"]] == [(2589, 100.0), (2592, -37.5)]
        down = api_client.get("/api/sync/auctions/", {"sort": "down"}).json()
        assert [r["item_id"] for r in down["results"]] == [2592, 2589]
        found = api_client.get("/api/sync/auctions/", {"q": "laine"}).json()
        assert [r["item_id"] for r in found["results"]] == [2592]
        horde = api_client.get("/api/sync/auctions/", {"house": "Forever-Horde", "sort": "price"}).json()
        assert horde["baseline"] is None
        assert [(r["price"], r["change"]) for r in horde["results"]] == [(999, None)]

    def test_item_history_is_per_house_oldest_first(self, api_client, as_user, gm, scans):
        as_user(gm)
        data = api_client.get("/api/sync/auctions/items/2589/", {"house": HOUSE}).json()
        assert [(p["price"], p["listed"]) for p in data["points"]] == [(50, 10), (80, 6), (100, 3)]
        assert (data["name"], data["min"], data["max"], data["average"]) == ("Étoffe de lin", 50, 100, 77)
        assert api_client.get("/api/sync/auctions/items/424242/").json()["points"] == []

    def test_empty_site_answers_an_empty_page(self, api_client, as_user, gm):
        as_user(gm)
        data = api_client.get("/api/sync/auctions/").json()
        assert (data["houses"], data["scan"], data["results"]) == ([], None, [])
