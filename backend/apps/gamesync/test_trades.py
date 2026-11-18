"""Achats et ventes à l'hôtel des ventes : reçus avec l'export de l'addon, montrés à leur auteur seul avec
l'historique de prix de l'objet, et rapprochés en reventes."""

from datetime import UTC, datetime, timedelta

import pytest

from apps.gamedata.models import Item

from . import services, trades
from .format import encode_export
from .models import AuctionTrade
from .test_rankings import character, gamedata  # noqa: F401 — `gamedata` : fixture

pytestmark = pytest.mark.django_db

T0 = int(datetime(2026, 11, 18, 15, 0, tzinfo=UTC).timestamp())
HOUR = 3600
REALM = "CAMWOW EU5 Realm 8 PvP"
FEATHER = 5165


def entry(n, kind, total, qty=None, hours=0, **extra):
    base = {"n": n, "t": T0 + hours * HOUR, "k": kind, "total": total, "item": FEATHER, "realm": REALM}
    if qty is not None:
        base["qty"] = qty
    return {**base, **extra}


def export(user, noted, install="pc-1"):
    char = character(f"Player-1-{user.pk}", "Thrall", counters={}, journal={}, events=[])
    # Chaque export porte une heure à lui : le même code ne s'importe pas deux fois.
    payload = {"v": 1, "install": install, "exported_at": T0 + len(str(noted)), "characters": [char]}
    services.import_code(user, encode_export({**payload, "trades": noted}), source="paste")


def history(api_client, item=FEATHER, house="PvP"):
    return api_client.get(f"/api/sync/auctions/items/{item}/", {"house": house}).json()


class TestImport:
    def test_trades_arrive_once_and_are_completed_by_a_later_export(self, member):
        bought = entry(1, "buy", 300, 3, src="commodity", char="Player-1-A", faction="Alliance")
        export(member, [bought, "bruit", {"n": 2}, entry(3, "sell", 0, 1), entry(4, "troc", 5, 1)])
        trade = AuctionTrade.objects.get()
        assert (trade.user, trade.kind, trade.item_id, trade.quantity, trade.price, trade.total) == (
            member, "buy", FEATHER, 3, 100, 300,
        )  # fmt: skip
        assert (trade.house, trade.realm, trade.source, trade.name) == ("PvP", REALM, "commodity", "")
        assert int(trade.at.timestamp()) == T0
        # Le même achat, nommé depuis ; et une vente de plus.
        export(member, [{**bought, "name": "Plume solécaille"}, entry(5, "sell", 500, 2, 2, fee=25)])
        assert AuctionTrade.objects.count() == 2
        trade.refresh_from_db()
        assert trade.name == "Plume solécaille"
        # Une autre installation numérote à part.
        export(member, [entry(1, "buy", 70, 1)], install="pc-2")
        assert AuctionTrade.objects.count() == 3

    def test_a_sale_known_by_its_name_only_finds_its_item(self, member):
        Item.objects.create(id=FEATHER, name="Plume solécaille", name_en="Sunscale Feather")
        Item.objects.create(id=1, name="Dague", name_en="Dagger")
        Item.objects.create(id=2, name="Dague", name_en="Dirk")
        export(
            member,
            [
                entry(1, "sell", 400, item=None, name="Plume solécaille", src="mail"),
                entry(2, "sell", 400, item=None, name="Dague", src="mail"),  # deux objets de ce nom
                entry(3, "sell", 400, item=None, name="Inconnu", src="mail"),
            ],
        )
        found = dict(AuctionTrade.objects.values_list("seq", "item_id"))
        assert found == {1: FEATHER, 2: None, 3: None}

    def test_amounts_out_of_range_and_dates_from_the_future_are_left_out(self, member):
        export(
            member,
            [
                entry(1, "buy", 10**13, 1),
                entry(2, "buy", 100, 1, hours=24 * 400),
                entry(3, "buy", 100.0, 2.0),  # entiers écrits en flottants : lus
                entry(4, "buy", 100, 1.5),  # quantité illisible : l'achat reste, sans quantité
                entry(5, "buy", True, 1),
            ],
        )
        assert list(AuctionTrade.objects.values_list("seq", "quantity", "price")) == [
            (3, 2, 50),
            (4, None, None),
        ]


class TestRoundTrips:
    def test_sales_are_matched_to_the_oldest_purchases(self, member):
        export(
            member,
            [
                entry(1, "buy", 1000, 10),  # 100 pièce
                entry(2, "buy", 2000, 10, 1),  # 200 pièce
                entry(3, "sell", 6000, 15, 5, fee=300),  # 10 à 100 et 5 à 200
                entry(4, "sell", 900, hours=6),  # quantité inconnue : hors bilan
                entry(5, "sell", 5000, 10, 7, fee=250),  # 5 restent en stock : la moitié seulement
                entry(6, "buy", 500, 2, 8),
            ],
        )
        trips, summary = trades.round_trips(list(AuctionTrade.objects.all()))
        first, second = trips
        assert (first["quantity"], first["cost"], first["revenue"], first["fee"], first["profit"]) == (
            15, 2000, 5700, 300, 3700,
        )  # fmt: skip
        assert (first["buy_price"], first["sell_price"], first["margin"], first["seconds"]) == (
            133, 400, 185.0, 5 * HOUR,
        )  # fmt: skip
        assert (second["quantity"], second["sold"], second["cost"], second["revenue"], second["profit"]) == (
            5, 10, 1000, 2375, 1375,
        )  # fmt: skip
        assert second["bought_at"] - first["bought_at"] == timedelta(hours=1)
        assert summary == {"trips": 2, "profit": 5075, "stock": 2, "stock_cost": 500}

    def test_a_sale_made_before_any_purchase_matches_nothing(self, member):
        export(member, [entry(1, "sell", 500, 5), entry(2, "buy", 100, 5, 1)])
        trips, summary = trades.round_trips(list(AuctionTrade.objects.all()))
        assert trips == []
        assert (summary["stock"], summary["stock_cost"], summary["profit"]) == (5, 100, 0)


class TestHistory:
    def test_the_price_history_carries_my_own_trades_only(self, api_client, as_user, member, gm):
        export(
            member,
            [entry(1, "buy", 300, 3), entry(2, "sell", 600, 3, 2, fee=30), entry(3, "buy", 80, 1, item=77)],
        )
        export(gm, [entry(1, "buy", 999, 1)], install="pc-gm")
        as_user(member)
        data = history(api_client)
        assert [(t["kind"], t["quantity"], t["price"], t["total"]) for t in data["trades"]] == [
            ("buy", 3, 100, 300),
            ("sell", 3, 200, 600),
        ]
        (trip,) = data["round_trips"]
        assert (trip["profit"], trip["margin"], trip["sale"]) == (270, 90.0, data["trades"][1]["id"])
        assert data["trade_summary"] == {"trips": 1, "profit": 270, "stock": 0, "stock_cost": 0}
        # Un objet sans transaction, puis l'autre joueur.
        empty = history(api_client, item=424242)
        assert (empty["trades"], empty["round_trips"], empty["trade_summary"]) == ([], [], None)
        as_user(gm)
        assert [t["total"] for t in history(api_client)["trades"]] == [999]

    def test_trades_stay_in_their_own_house(self, api_client, as_user, member):
        export(member, [entry(1, "buy", 300, 3), entry(2, "buy", 50, 1, realm="Forever")])
        as_user(member)
        assert trades.for_item(member, FEATHER, "PvP")["trades"][0]["total"] == 300
        assert len(trades.for_item(member, FEATHER, "PvP")["trades"]) == 1
        assert [t["total"] for t in trades.for_item(member, FEATHER, "Forever-Alliance")["trades"]] == [50]
