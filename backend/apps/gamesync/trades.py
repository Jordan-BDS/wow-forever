"""Achats et ventes des joueurs à l'hôtel des ventes : reçus de l'addon avec l'export, montrés à leur auteur
seul sur la courbe de prix d'un objet, avec le bilan de chaque revente (achat puis vente du même objet).

Ce que l'addon envoie est décrit en tête de `addon/WoWForeverGuilde/Collectors/Trades.lua`."""

from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.gamedata.models import Item

from .models import AuctionTrade

MAX_ENTRIES = 2000  # entrées lues dans un export : l'addon en garde 1000
MAX_AMOUNT = 10**12
MAX_QUANTITY = 10**7
MAX_ID = 2**31 - 1
SHOWN = 500  # transactions d'un objet rendues avec son historique, les plus récentes
FUTURE = timedelta(days=1)  # une horloge de PC en avance, pas plus
UPDATED = (
    "at", "kind", "source", "item_id", "name", "quantity", "price", "total", "fee", "deposit",
    "character_guid", "realm", "house", "faction",
)  # fmt: skip


def _whole(value: Any, limit: int) -> int | None:
    """Un entier positif ou nul, borné. Le JSON de l'addon peut écrire un entier comme un flottant."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # noqa: PLR0124 (NaN)
        return None
    if value != int(value) or not 0 <= value <= limit:
        return None
    return int(value)


def _text(value: Any, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _stamp(value: Any) -> datetime | None:
    stamp = _whole(value, 2**40)
    if not stamp:
        return None
    try:
        return datetime.fromtimestamp(stamp, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _house(realm: str) -> str:
    from .auctions import canonical_house  # import local : auctions.py lit ce module

    return canonical_house(realm)


def _parse(raw: Any, latest: datetime) -> dict | None:
    """Les champs d'une entrée de l'addon, ou None si elle est illisible."""
    if not isinstance(raw, dict):
        return None
    seq, at = _whole(raw.get("n"), MAX_ID), _stamp(raw.get("t"))
    total, kind = _whole(raw.get("total"), MAX_AMOUNT), raw.get("k")
    if not seq or not at or at > latest or not total or kind not in (AuctionTrade.BUY, AuctionTrade.SELL):
        return None
    quantity = _whole(raw.get("qty"), MAX_QUANTITY) or None
    realm = _text(raw.get("realm"), 96)
    return {
        "seq": seq,
        "at": at,
        "kind": kind,
        "source": _text(raw.get("src"), 12),
        "item_id": _whole(raw.get("item"), MAX_ID) or None,
        "name": _text(raw.get("name"), 120),
        "quantity": quantity,
        "price": total // quantity if quantity else None,
        "total": total,
        "fee": _whole(raw.get("fee"), MAX_AMOUNT) or 0,
        "deposit": _whole(raw.get("deposit"), MAX_AMOUNT) or 0,
        "character_guid": _text(raw.get("char"), 64),
        "realm": realm,
        "house": _house(realm),
        "faction": _text(raw.get("faction"), 16),
    }


def _items_by_name(names: set[str]) -> dict[str, int]:
    """Nom du jeu → objet de l'index, pour les ventes que l'addon n'a pas su rattacher. Un nom porté par
    plusieurs objets ne désigne personne."""
    found: dict[str, set[int]] = {}
    if names:
        rows = Item.objects.filter(Q(name__in=names) | Q(name_en__in=names))
        for item_id, name, name_en in rows.values_list("id", "name", "name_en"):
            for label in {name, name_en} & names:
                found.setdefault(label, set()).add(item_id)
    return {name: next(iter(ids)) for name, ids in found.items() if len(ids) == 1}


def import_trades(user, install_id: Any, raw: Any) -> int:
    """Range les transactions d'un export. Une entrée déjà reçue (même installation, même numéro) est mise à
    jour si l'addon l'a complétée. Rend le nombre d'entrées créées ou changées."""
    install_id = _text(install_id, 64)
    if not install_id or not isinstance(raw, list):
        return 0
    latest = timezone.now() + FUTURE
    parsed: dict[int, dict] = {}
    for entry in raw[-MAX_ENTRIES:]:
        fields = _parse(entry, latest)
        if fields:
            parsed[fields["seq"]] = fields
    if not parsed:
        return 0
    by_name = _items_by_name({f["name"] for f in parsed.values() if not f["item_id"] and f["name"]})
    for fields in parsed.values():
        if not fields["item_id"]:
            fields["item_id"] = by_name.get(fields["name"])
    known = {
        trade.seq: trade
        for trade in AuctionTrade.objects.filter(user=user, install_id=install_id, seq__in=parsed.keys())
    }
    created, changed = [], []
    for seq, fields in parsed.items():
        trade = known.get(seq)
        if trade is None:
            created.append(AuctionTrade(user=user, install_id=install_id, **fields))
        elif any(getattr(trade, name) != fields[name] for name in UPDATED):
            for name in UPDATED:
                setattr(trade, name, fields[name])
            changed.append(trade)
    AuctionTrade.objects.bulk_create(created, ignore_conflicts=True)
    if changed:
        AuctionTrade.objects.bulk_update(changed, UPDATED)
    return len(created) + len(changed)


def round_trips(trades: list[AuctionTrade]) -> tuple[list[dict], dict]:
    """Les reventes : chaque vente est rapprochée des achats les plus anciens encore en stock (premier entré,
    premier sorti). Rend les reventes et le bilan : bénéfice cumulé, et ce qui reste en stock avec son coût.

    Recette d'une vente : son prix moins la commission de l'hôtel. Le dépôt, rendu à la vente, ne compte pas ;
    celui d'une enchère expirée n'est pas connu. Une transaction sans quantité ne se rapproche de rien, et ce
    qui est vendu sans avoir été acheté à l'hôtel (butin, artisanat) n'entre pas dans le bilan."""
    lots: deque[list] = deque()  # [achat, unités restantes]
    trips = []
    for trade in sorted(trades, key=lambda t: (t.at, t.kind != AuctionTrade.BUY, t.pk or 0)):
        if not trade.quantity:
            continue
        if trade.kind == AuctionTrade.BUY:
            lots.append([trade, trade.quantity])
            continue
        need, cost, first = trade.quantity, 0.0, None
        while need and lots:
            lot = lots[0]
            buy, taken = lot[0], min(need, lot[1])
            first = first or buy
            cost += buy.total * taken / buy.quantity
            need -= taken
            lot[1] -= taken
            if not lot[1]:
                lots.popleft()
        matched = trade.quantity - need
        if not matched or first is None:
            continue
        share = matched / trade.quantity
        spent, fee = round(cost), round(trade.fee * share)
        revenue = round((trade.total - trade.fee) * share)
        trips.append(
            {
                "sale": trade.pk,
                "bought_at": first.at,
                "sold_at": trade.at,
                "quantity": matched,
                "sold": trade.quantity,
                "buy_price": round(spent / matched),
                "sell_price": trade.price,
                "cost": spent,
                "fee": fee,
                "revenue": revenue,
                "profit": revenue - spent,
                "margin": round((revenue - spent) * 1000 / spent) / 10 if spent else None,
                "seconds": int((trade.at - first.at).total_seconds()),
            }
        )
    summary = {
        "trips": len(trips),
        "profit": sum(trip["profit"] for trip in trips),
        "stock": sum(left for _, left in lots),
        "stock_cost": round(sum(buy.total * left / buy.quantity for buy, left in lots)),
    }
    return trips, summary


def _same_house(trade_house: str, house: str) -> bool:
    """Un hôtel du site porte le nom écrit par l'addon de scan, une transaction celui du royaume : égaux pour
    l'hôtel PvP, sinon le nom de l'hôtel commence par celui du royaume. Sans l'un des deux, on ne trie pas."""
    if not trade_house or not house:
        return True
    return house.casefold().startswith(trade_house.casefold())


def for_item(user, item_id: int, house: str) -> dict:
    """Les transactions du joueur sur un objet dans un hôtel, de la plus ancienne à la plus récente, ses
    reventes et leur bilan."""
    if not user or not user.is_authenticated:
        return {"trades": [], "round_trips": [], "trade_summary": None}
    mine = [
        trade
        for trade in AuctionTrade.objects.filter(user=user, item_id=item_id).order_by("at", "id")
        if _same_house(trade.house, house)
    ]
    trips, summary = round_trips(mine)
    return {
        "trades": [
            {
                "id": trade.pk,
                "at": trade.at,
                "kind": trade.kind,
                "source": trade.source,
                "quantity": trade.quantity,
                "price": trade.price,
                "total": trade.total,
                "fee": trade.fee,
            }
            for trade in mine[-SHOWN:]
        ],
        "round_trips": trips,
        "trade_summary": summary if mine else None,
    }
