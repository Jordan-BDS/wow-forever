from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.gamedata.models import Item, Profession, Recipe

from . import auctions, services
from .models import AuctionPrice, AuctionScan, FavoriteRecipe

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
    def test_every_member_sends_and_reads_but_not_a_visitor(self, api_client, as_user, member, officer, gm):
        for ago, user in enumerate((member, officer, gm)):
            as_user(user)
            assert post_scan(api_client, [[2589, 100, 3]], timedelta(hours=ago)).status_code == 201
            assert api_client.get("/api/sync/auctions/").status_code == 200
            assert api_client.get("/api/sync/auctions/items/2589/").status_code == 200
        assert set(AuctionScan.objects.values_list("user", flat=True)) == {member.pk, officer.pk, gm.pk}
        api_client.force_authenticate(None)
        assert post_scan(api_client, [[2589, 100, 3]], timedelta(hours=5)).status_code in (401, 403)
        assert api_client.get("/api/sync/auctions/").status_code in (401, 403)
        assert AuctionScan.objects.count() == 3

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

    def test_companion_of_a_member_is_told_it_may_send_and_sends(self, api_client, member):
        api_client.credentials(HTTP_AUTHORIZATION=f"Companion {companion_token(member)}")
        assert api_client.get("/api/sync/auctions/rights/").json() == {"upload": True}
        assert post_scan(api_client, [[2589, 100, 3]]).status_code == 201
        assert AuctionScan.objects.get().user == member

    def test_the_right_to_send_has_a_single_rule(self, api_client, as_user, member, monkeypatch):
        # Changer qui a le droit se fait dans `can_upload` seulement : le drapeau et les vues suivent.
        monkeypatch.setattr(auctions, "can_upload", lambda user: False)
        as_user(member)
        assert api_client.get("/api/sync/auctions/rights/").json() == {"upload": False}
        assert post_scan(api_client, [[2589, 100, 3]]).status_code == 403
        assert api_client.get("/api/sync/auctions/").status_code == 403
        assert api_client.get("/api/sync/auctions/items/2589/").status_code == 403

    def test_old_scans_are_thinned_to_one_per_day_then_deleted(self, gm):
        old = [timedelta(days=40, hours=h) for h in (3, 2, 0)]
        recent = [timedelta(days=13), timedelta(days=13, hours=-1), timedelta(hours=2), timedelta(0)]
        for ago in (timedelta(days=200), *old, *recent):
            auctions.store_scan(gm, HOUSE, stamp(ago), [[2589, 100, 3]])
        kept = [NOW - scan.scanned_at for scan in AuctionScan.objects.order_by("scanned_at")]
        # Il y a 200 jours : supprimé (plus de six mois). Il y a 40 jours : le dernier scan de chaque jour
        # reste. Depuis moins de 14 jours : tous gardés.
        last_of_day = {timezone.localtime(NOW - ago).date(): ago for ago in old}
        assert kept == [*sorted(last_of_day.values(), reverse=True), *sorted(recent, reverse=True)]
        assert len(kept) < 7
        assert AuctionPrice.objects.count() == len(kept)

    def test_periodic_cleaning_reaches_houses_nobody_scans_anymore(self, gm):
        dead = AuctionScan.objects.create(
            house="Abandonné", scanned_at=NOW - timedelta(days=200), user=gm, items=1
        )
        AuctionPrice.objects.create(scan=dead, item_id=2589, price=1, listed=1)
        auctions.store_scan(gm, HOUSE, stamp(timedelta(0)), [[2589, 100, 3]])  # ne nettoie que son hôtel
        assert AuctionScan.objects.count() == 2
        assert auctions.prune_due() == 1
        assert [scan.house for scan in AuctionScan.objects.all()] == [HOUSE]
        assert AuctionPrice.objects.count() == 1
        # Une fois par heure au plus : le balayage tourne toutes les minutes.
        AuctionScan.objects.create(house="Abandonné", scanned_at=NOW - timedelta(days=200), user=gm, items=0)
        assert auctions.prune_due() == 0
        assert AuctionScan.objects.count() == 2

    def test_two_scans_of_a_house_are_at_least_half_an_hour_apart(self, api_client, as_user, gm, member):
        as_user(gm)
        assert post_scan(api_client, [[2589, 100, 3]], timedelta(hours=2)).status_code == 201
        as_user(member)
        # Trop près, avant comme après (un scan plus ancien peut arriver plus tard) : refusé comme un scan
        # déjà reçu, que le compagnon retient sans le renvoyer. Le premier reçu reste.
        for ago in (timedelta(hours=2, minutes=29), timedelta(hours=1, minutes=31)):
            response = post_scan(api_client, [[2589, 1, 1]], ago)
            assert response.status_code == 409
            assert "30 minutes" in response.json()["detail"]
        assert post_scan(api_client, [[2589, 1, 1]], timedelta(hours=2)).json() == {
            "detail": "Ce scan a déjà été reçu."
        }
        assert AuctionScan.objects.get().user == gm
        # À 30 minutes pile, et dans un autre hôtel au même moment : acceptés.
        assert post_scan(api_client, [[2589, 100, 3]], timedelta(hours=2, minutes=30)).status_code == 201
        assert post_scan(api_client, [[2589, 100, 3]], timedelta(hours=1, minutes=30)).status_code == 201
        assert post_scan(api_client, [[2589, 100, 3]], timedelta(hours=2), "Forever-Horde").status_code == 201
        assert AuctionScan.objects.count() == 4

    def test_every_house_named_pvp_is_one_house(self, api_client, as_user, gm, member, items):
        as_user(gm)
        first = post_scan(api_client, [[2589, 80, 6]], timedelta(hours=2), "CAMWOW EU5 Realm 8 PvP-Alliance")
        assert (first.status_code, first.json()["house"]) == (201, "PvP")
        as_user(member)
        # Autre royaume, autre faction, autre casse : le même hôtel, donc la même règle d'écart.
        assert (
            post_scan(
                api_client, [[2589, 1, 1]], timedelta(hours=1, minutes=50), "Realm 3 pvp-Horde"
            ).status_code
            == 409
        )
        assert post_scan(api_client, [[2589, 100, 3]], timedelta(0), " EU2  PVP ").status_code == 201
        assert post_scan(api_client, [[2589, 5, 1]], timedelta(0), "Realm 1 PvE-Alliance").status_code == 201
        assert set(AuctionScan.objects.values_list("house", flat=True)) == {"PvP", "Realm 1 PvE-Alliance"}
        # La lecture suit : un ancien nom demandé par la page ou un lien mène à l'hôtel PvP et à sa courbe.
        data = api_client.get("/api/sync/auctions/", {"house": "CAMWOW EU5 Realm 8 PvP-Alliance"}).json()
        assert (data["house"], data["scan"]["items"], data["baseline"]["items"]) == ("PvP", 1, 1)
        assert sorted((h["house"], h["scans"]) for h in data["houses"]) == [
            ("PvP", 2),
            ("Realm 1 PvE-Alliance", 1),
        ]
        history = api_client.get("/api/sync/auctions/items/2589/", {"house": "Realm 9 PvP-Horde"}).json()
        assert (history["house"], [p["price"] for p in history["points"]]) == ("PvP", [80, 100])

    def test_migration_merges_the_pvp_houses_already_stored(self, gm):
        from importlib import import_module

        from django.apps import apps

        def scan(house, ago, items):
            return AuctionScan.objects.create(house=house, scanned_at=NOW - ago, user=gm, items=items)

        scan("CAMWOW EU5 Realm 8 PvP-Alliance", timedelta(hours=3), 1)
        scan("Realm 3 pvp-Horde", timedelta(hours=1), 2)
        scan("Realm 4 PVP-Horde", timedelta(hours=3), 3)  # même instant qu'un autre : le premier reste
        scan("Realm 1 PvE-Alliance", timedelta(hours=3), 4)
        import_module("apps.gamesync.migrations.0010_auction_pvp_house").merge_pvp_houses(apps, None)
        assert sorted(AuctionScan.objects.values_list("house", "items")) == [
            ("PvP", 1),
            ("PvP", 2),
            ("Realm 1 PvE-Alliance", 4),
        ]

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

    def test_search_reads_both_names_whatever_the_accents(self, api_client, as_user, gm, scans):
        # Le scan nomme l'objet par son ID : seul l'index du site lui donne un nom, français et anglais.
        Item.objects.create(
            id=1716, name="Robe du Magus", name_en="Robe of the Magi", quality=3, icon="inv_chest_cloth_38"
        )
        auctions.store_scan(gm, HOUSE, stamp(timedelta(minutes=-45)), [[1716, 35000, 4], [2589, 100, 3]])
        as_user(gm)

        def found(q):
            data = api_client.get("/api/sync/auctions/", {"q": q}).json()
            assert all("search" not in r for r in data["results"])
            return [r["item_id"] for r in data["results"]]

        assert found("robe of the magi") == [1716]  # nom anglais
        assert found("  Robe  du magus ") == [1716]  # nom français, espaces en trop
        assert found("etoffe") == [2589] and found("ÉTOFFE DE LIN") == [2589]  # accents et casse
        assert found("1716") == [1716]
        assert found("of the linen") == []  # pas à cheval sur les deux noms

    def test_biggest_movements_are_estimated_from_the_number_of_auctions(
        self, api_client, as_user, gm, items
    ):
        Item.objects.create(id=4306, name="Étoffe de soie", quality=1, icon="inv_fabric_silk_01")
        before = [[2589, 50, 10], [2592, 400, 5], [4306, 900, 4], [7000, 30, None]]
        auctions.store_scan(gm, HOUSE, stamp(timedelta(hours=1)), before)
        after = [[2589, 60, 2], [2592, 300, 12], [7000, 30, 8], [8000, 5, 3]]
        auctions.store_scan(gm, HOUSE, stamp(timedelta(0)), after)
        as_user(gm)
        # Enchères parties : la soie a disparu du scan (4 × 900), le lin est passé de 10 à 2 (8 × 50, au prix
        # de référence). La plus grosse valeur d'abord ; l'objet disparu garde son dernier prix, zéro enchère.
        sold = api_client.get("/api/sync/auctions/", {"sort": "sold"}).json()
        assert [
            (r["item_id"], r["previous_listed"], r["listed"], r["listed_change"], r["moved"], r["gone"])
            for r in sold["results"]
        ] == [(4306, 4, 0, -4, 3600, True), (2589, 10, 2, -8, 400, False)]
        assert (sold["results"][0]["price"], sold["results"][0]["change"]) == (900, None)
        # Enchères arrivées, au prix actuel : la laine de 5 à 12 (7 × 300). Un objet nouveau ou dont le nombre
        # d'enchères n'était pas connu n'a pas de mouvement.
        posted = api_client.get("/api/sync/auctions/", {"sort": "posted"}).json()
        assert [(r["item_id"], r["listed_change"], r["moved"]) for r in posted["results"]] == [
            (2592, 7, 2100)
        ]
        # Les autres tris ne montrent pas les disparus, mais portent le mouvement de chaque objet.
        names = api_client.get("/api/sync/auctions/").json()
        assert names["total"] == 4 and all(r["gone"] is False for r in names["results"])
        rows = {r["item_id"]: r for r in names["results"]}
        assert (rows[2589]["listed_change"], rows[8000]["listed_change"], rows[7000]["listed_change"]) == (
            -8,
            None,
            None,
        )
        # La recherche vaut aussi pour les disparus ; sans scan de référence, aucun mouvement.
        found = api_client.get("/api/sync/auctions/", {"sort": "sold", "q": "soie"}).json()
        assert [r["item_id"] for r in found["results"]] == [4306]
        auctions.store_scan(gm, "Forever-Horde", stamp(timedelta(0)), [[2589, 999, 1]])
        horde = api_client.get("/api/sync/auctions/", {"house": "Forever-Horde", "sort": "sold"}).json()
        assert horde["results"] == []

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


class TestRecipes:
    @pytest.fixture
    def recipes(self, gm, items):
        Item.objects.create(id=2996, name="Rouleau d'étoffe de lin", quality=1, icon="inv_fabric_linen_02")
        Item.objects.create(id=2570, name="Cape en lin", name_en="Linen Cloak", quality=1, icon="inv_cape")
        tailoring = Profession.objects.create(slug="tailoring", name="Couture", kind="primary")
        Recipe.objects.create(
            id=2963,
            profession=tailoring,
            name="Rouleau d'étoffe de lin",
            product_id=2996,
            reagents=[{"item_id": 2589, "name": "Étoffe de lin", "count": 2}],
        )
        Recipe.objects.create(
            id=2387,
            profession=tailoring,
            name="Cape en lin",
            product_id=2570,
            reagents=[
                {"item_id": 2996, "name": "Rouleau d'étoffe de lin", "count": 1},
                {"item_id": 2320, "name": "Fil grossier", "count": 1},  # vendu par les PNJ, jamais à l'HV
            ],
        )
        auctions.store_scan(gm, HOUSE, stamp(timedelta(hours=1)), [[2589, 1, 1]])
        auctions.store_scan(gm, HOUSE, stamp(timedelta(0)), [[2589, 100, 3], [2996, 350, 5], [2570, 900]])

    def test_favorites_are_personal_and_closed_to_visitors(self, api_client, as_user, gm, member, recipes):
        assert api_client.get("/api/sync/auctions/recipes/").status_code in (401, 403)
        assert api_client.put("/api/sync/auctions/recipes/2963/").status_code in (401, 403)
        as_user(gm)
        assert api_client.put("/api/sync/auctions/recipes/424242/").status_code == 404
        for _ in range(2):  # suivre deux fois ne crée qu'un favori
            assert api_client.put("/api/sync/auctions/recipes/2963/").status_code == 204
        FavoriteRecipe.objects.create(user=member, recipe_id=2387)
        data = api_client.get("/api/sync/auctions/recipes/").json()
        assert (data["searching"], data["favorites"]) == (False, 1)
        assert [(r["recipe_id"], r["favorite"]) for r in data["results"]] == [(2963, True)]
        assert api_client.delete("/api/sync/auctions/recipes/2963/").status_code == 204
        assert api_client.get("/api/sync/auctions/recipes/").json()["results"] == []
        assert FavoriteRecipe.objects.filter(user=member).count() == 1
        # Un membre suit ses propres recettes, sans voir celles des autres.
        as_user(member)
        data = api_client.get("/api/sync/auctions/recipes/").json()
        assert [(r["recipe_id"], r["favorite"]) for r in data["results"]] == [(2387, True)]
        assert api_client.put("/api/sync/auctions/recipes/2963/").status_code == 204
        assert FavoriteRecipe.objects.filter(user=member).count() == 2

    def test_cost_and_profit_come_from_the_latest_scan(self, api_client, as_user, gm, recipes):
        as_user(gm)
        auctions.set_favorite(gm, 2963, True)
        data = api_client.get("/api/sync/auctions/recipes/").json()
        assert (data["house"], data["scan"]["items"]) == (HOUSE, 3)
        (row,) = data["results"]
        assert (row["profession"], row["cost"], row["revenue"], row["profit"], row["margin"]) == (
            "Couture",
            200,
            350,
            150,
            75.0,
        )
        assert (row["product"]["price"], row["product"]["listed"], row["missing"]) == (350, 5, 0)
        (reagent,) = row["reagents"]
        assert (reagent["name"], reagent["count"], reagent["price"], reagent["total"]) == (
            "Étoffe de lin",
            2,
            100,
            200,
        )
        assert reagent["icon_url"].endswith("inv_fabric_linen_01.jpg")

    def test_search_shows_costs_and_reagents_missing_from_the_house(self, api_client, as_user, gm, recipes):
        as_user(gm)
        auctions.set_favorite(gm, 2963, True)
        data = api_client.get("/api/sync/auctions/recipes/", {"q": "linen cloak"}).json()
        assert data["searching"] is True
        (row,) = data["results"]
        # Le fil n'est pas à l'HV : le coût ne compte que le rouleau, et le dit.
        assert (row["recipe_id"], row["favorite"], row["cost"], row["missing"]) == (2387, False, 350, 1)
        assert (row["revenue"], row["profit"]) == (900, 550)
        assert [(r["name"], r["price"]) for r in row["reagents"]] == [
            ("Rouleau d'étoffe de lin", 350),
            ("Fil grossier", None),
        ]
        both = api_client.get("/api/sync/auctions/recipes/", {"q": "lin"}).json()
        assert [(r["recipe_id"], r["favorite"]) for r in both["results"]] == [(2387, False), (2963, True)]
        # Une seule lettre ne cherche pas : ce sont les favorites.
        one = api_client.get("/api/sync/auctions/recipes/", {"q": "l"}).json()
        assert (one["searching"], [r["recipe_id"] for r in one["results"]]) == (False, [2963])

    def test_without_any_scan_recipes_have_no_price(self, api_client, as_user, gm):
        tailoring = Profession.objects.create(slug="tailoring", name="Couture", kind="primary")
        Recipe.objects.create(
            id=2963, profession=tailoring, name="Rouleau", reagents=[{"item_id": 2589, "count": 2}]
        )
        as_user(gm)
        auctions.set_favorite(gm, 2963, True)
        data = api_client.get("/api/sync/auctions/recipes/").json()
        (row,) = data["results"]
        assert (data["scan"], row["product"], row["cost"], row["profit"], row["missing"]) == (
            None,
            None,
            None,
            None,
            1,
        )
        assert row["reagents"][0]["name"] == "Objet 2589"
