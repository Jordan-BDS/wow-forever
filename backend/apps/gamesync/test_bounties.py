"""Primes posées à la main : pose, comptage des kills exportés par l'addon, partage, registre des dettes."""

from datetime import UTC, datetime, timedelta

import pytest
from django.core.cache import cache

from apps.gamedata.models import Item

from . import bounties
from .models import Bounty, BountyPayment
from .test_rankings import PARIS, character, gamedata, import_for  # noqa: F401 — `gamedata` : fixture

pytestmark = pytest.mark.django_db

T0 = int(datetime(2026, 9, 21, 17, 0, tzinfo=PARIS).timestamp())
POSTED = datetime.fromtimestamp(T0, tz=UTC)
PO = bounties.COPPER


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()


def pk(seconds, name, **extra):
    return {"k": "pk", "t": T0 + seconds, "name": name, "zone": "Durotar", **extra}


def hunt(user, guid, name, *events):
    import_for(user, character(guid, name, counters={"pk": len(events)}, journal={}, events=events))
    cache.clear()


def bounty(poster, target="Garrosh Hurlenfer", gold=10, max_kills=2, **extra):
    return Bounty.objects.create(
        poster=poster, target_name=target, amount=gold * PO, max_kills=max_kills, created_at=POSTED, **extra
    )


class TestPosting:
    def test_any_member_posts_a_bounty_but_not_a_visitor(self, api_client, as_user, member):
        assert api_client.get("/api/sync/bounties/").status_code in (401, 403)
        as_user(member)
        body = {
            "target": "  Garrosh   Hurlenfer ",
            "gold": 50,
            "max_kills": 5,
            "note": "Il campe Tarren Mill",
        }
        response = api_client.post("/api/sync/bounties/", body, format="json")
        assert response.status_code == 201
        posted = response.json()["bounties"][0]
        assert (posted["target"], posted["amount"], posted["max_kills"], posted["status"]) == (
            "Garrosh Hurlenfer",
            50 * PO,
            5,
            "open",
        )
        assert posted["poster"]["id"] == member.pk and posted["can_cancel"] and posted["can_pay"]
        # Une seule prime en cours par commanditaire et par cible.
        again = api_client.post(
            "/api/sync/bounties/", {"target": "garrosh hurlenfer", "gold": 1}, format="json"
        )
        assert again.status_code == 400 and "déjà" in again.json()["detail"]

    @pytest.mark.parametrize(
        "body",
        [
            {"target": "G", "gold": 10},
            {"target": "Garrosh"},  # ni or ni objet
            {"target": "Garrosh", "gold": -1},
            {"target": "Garrosh", "gold": 10, "max_kills": 0},
            {"target": "Garrosh", "gold": "10"},
            {"target": "Garrosh", "item_id": 424242},  # objet inconnu
        ],
    )
    def test_unreadable_bounties_are_refused(self, api_client, as_user, member, body):
        as_user(member)
        assert api_client.post("/api/sync/bounties/", body, format="json").status_code == 400
        assert not Bounty.objects.exists()

    def test_default_is_one_kill_and_items_can_be_the_reward(self, api_client, as_user, member):
        as_user(member)
        body = {"target": "Sylvanas", "item_id": 16842, "item_count": 3}
        posted = api_client.post("/api/sync/bounties/", body, format="json").json()["bounties"][0]
        assert (posted["max_kills"], posted["amount"], posted["item_count"]) == (1, 0, 3)
        assert posted["item"]["name"] == "Couronne de la Terre"


class TestCounting:
    def test_kills_are_shared_capped_and_owed_to_the_hunters(
        self, api_client, as_user, gm, member, other_member
    ):
        posted = bounty(gm)
        hunt(
            member,
            "Player-1-T",
            "Thrall",
            pk(-600, "Garrosh Hurlenfer"),  # avant la pose de la prime
            pk(600, "Garrosh"),  # prénom seul : la même cible
            pk(700, "Garrosh Autre"),  # un autre joueur
            pk(800, "Garrosh Hurlenfer", bg=True),  # champ de bataille
            pk(2000, "Garrosh Hurlenfer"),  # deuxième kill, seul
            pk(4000, "Garrosh Hurlenfer"),  # troisième : au-delà du nombre payé
        )
        hunt(other_member, "Player-1-G", "Garona", pk(605, "Garrosh Hurlenfer"))  # le premier kill, à deux
        as_user(gm)
        data = api_client.get("/api/sync/bounties/").json()
        found = data["bounties"][0]
        assert found["status"] == "done" and len(found["kills"]) == 2
        first = found["kills"][-1]  # les plus récents d'abord
        assert [(h["user"]["id"], h["amount"]) for h in first["hunters"]] == [
            (member.pk, 5 * PO),
            (other_member.pk, 5 * PO),
        ]
        assert [(d["hunter"]["id"], d["kills"], d["owed"]) for d in found["dues"]] == [
            (member.pk, 2, 15 * PO),
            (other_member.pk, 1, 5 * PO),
        ]
        assert [(row["from"]["id"], row["to"]["id"], row["amount"]) for row in data["ledger"]] == [
            (gm.pk, member.pk, 15 * PO),
            (gm.pk, other_member.pk, 5 * PO),
        ]

        # Seul le commanditaire (ou le GM) déclare un paiement ; il solde ce qui reste dû au chasseur.
        as_user(other_member)
        url = f"/api/sync/bounties/{posted.pk}/payments/"
        assert api_client.post(url, {"hunter_id": other_member.pk}, format="json").status_code == 400
        as_user(gm)
        paid = api_client.post(url, {"hunter_id": member.pk}, format="json").json()
        assert [(row["to"]["id"], row["amount"]) for row in paid["ledger"]] == [(other_member.pk, 5 * PO)]
        assert BountyPayment.objects.get().amount == 15 * PO
        assert (
            api_client.post(url, {"hunter_id": member.pk}, format="json").status_code == 400
        )  # plus rien dû

    def test_the_poster_is_not_a_hunter_of_their_own_bounty(self, gm, member):
        posted = bounty(gm, max_kills=1)
        hunt(gm, "Player-1-X", "Rexxar", pk(600, "Garrosh Hurlenfer"))  # seul : la prime n'est pas consommée
        assert bounties.bounty_kills(posted, bounties.player_kills()) == []
        hunt(member, "Player-1-T", "Thrall", pk(605, "Garrosh Hurlenfer"), pk(3000, "Garrosh Hurlenfer"))
        kills = bounties.bounty_kills(posted, bounties.player_kills())
        assert len(kills) == 1  # un kill payé au plus
        assert [(s["who"]["user"]["id"], s["amount"]) for s in kills[0]["hunters"]] == [(member.pk, 10 * PO)]

    def test_items_that_do_not_divide_go_to_the_first_hunters(self, gm, member, other_member):
        crown = Item.objects.get(pk=16842)
        posted = bounty(gm, gold=0, max_kills=1, item=crown, item_count=3)
        hunt(member, "Player-1-T", "Thrall", pk(600, "Garrosh Hurlenfer"))
        hunt(other_member, "Player-1-G", "Garona", pk(610, "Garrosh Hurlenfer"))
        report = bounties.report(gm)
        assert [(d["hunter"]["id"], d["items_owed"]) for d in report["bounties"][0]["dues"]] == [
            (member.pk, 2),
            (other_member.pk, 1),
        ]
        line = report["ledger"][0]
        assert (line["amount"], line["items"][0]["name"], line["items"][0]["count"]) == (0, crown.name, 2)
        assert posted.max_kills == 1

    def test_cancelling_keeps_what_is_already_owed(self, api_client, as_user, gm, member, officer):
        posted = bounty(gm, max_kills=5)
        hunt(member, "Player-1-T", "Thrall", pk(600, "Garrosh Hurlenfer"))
        url = f"/api/sync/bounties/{posted.pk}/cancel/"
        as_user(member)
        assert api_client.post(url).status_code == 400  # ni commanditaire ni officier
        as_user(officer)
        cancelled = api_client.post(url).json()["bounties"][0]
        assert cancelled["status"] == "cancelled" and not cancelled["can_cancel"]
        assert [(d["hunter"]["id"], d["owed"]) for d in cancelled["dues"]] == [(member.pk, 10 * PO)]
        # Un kill fait après l'annulation n'est pas payé.
        posted.refresh_from_db()
        posted.cancelled_at = POSTED + timedelta(seconds=900)
        posted.save()
        hunt(member, "Player-1-T", "Thrall", pk(600, "Garrosh Hurlenfer"), pk(2000, "Garrosh Hurlenfer"))
        assert len(bounties.bounty_kills(posted, bounties.player_kills())) == 1
