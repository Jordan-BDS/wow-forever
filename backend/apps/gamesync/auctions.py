"""
Prix de l'hôtel des ventes : le compagnon de chaque membre envoie chaque scan complet lu dans le fichier de
l'addon de scan, le site en tire l'historique de chaque objet. Envoi et lecture ouverts à tous les membres
connectés.

Un hôtel par jeu de règles : tout nom d'hôtel qui contient « pvp » désigne le même hôtel (`canonical_house`),
quels que soient le royaume et la faction que l'addon de scan y écrit. Deux scans d'un même hôtel sont espacés
d'au moins `MIN_GAP` : le premier reçu reste, l'autre est refusé comme un doublon. Les scans sont tous gardés
`KEEP_ALL`, puis un par jour jusqu'à `KEEP_DAILY`, puis supprimés (`prune`).
"""

import logging
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.gamedata.models import Item, Recipe
from apps.gamedata.stats import icon_url

from . import auction_categories
from .models import (
    AuctionPrice,
    AuctionReport,
    AuctionScan,
    CompanionDevice,
    FavoriteItem,
    FavoriteRecipe,
)

MAX_ITEMS = 60_000
RECIPE_RESULTS = 30  # recettes montrées par une recherche
MAX_PRICE = 10**12
MAX_LISTED = 10**7
MAX_FAVORITE_ITEMS = 500  # objets suivis par joueur
PAGE_SIZE = 100
HISTORY_POINTS = 500
MIN_GAP = timedelta(minutes=30)  # écart minimal entre deux scans d'un même hôtel
# Un scan partiel (des recherches prises pour un scan, une petite base Auctionator) : moins de cette part des
# objets du dernier scan de l'hôtel, quand celui-ci en compte au moins `PARTIAL_FLOOR`.
PARTIAL_SHARE = 0.6
PARTIAL_FLOOR = 1000
KEEP_ALL = timedelta(days=14)  # tous les scans sont gardés ce temps-là, puis un par jour
KEEP_DAILY = timedelta(days=183)  # au-delà (six mois), les scans sont supprimés
PVP_HOUSE = "PvP"  # l'hôtel de tous les royaumes PvP : même jeu de règles, même hôtel
PRUNE_EVERY = 3600  # s : le balayage périodique ne nettoie pas plus souvent
ROWS_TTL = 900  # s : la comparaison de deux scans (immuables) est gardée, seuls les noms peuvent bouger
ROWS_KEPT = (
    4  # comparaisons gardées par processus : le dernier scan contre ses trois références, et une de plus
)
ID_BATCH = 5000  # objets par requête sur l'index (SQLite borne le nombre de paramètres)
ALERT_FRESH = timedelta(hours=6)  # un scan plus vieux ne déclenche pas d'alerte de prix

logger = logging.getLogger(__name__)

# Référence de la variation : le scan précédent, ou le dernier scan vieux d'au moins un jour / une semaine.
BASELINES = {"prev": None, "day": timedelta(days=1), "week": timedelta(days=7)}
# « sold » et « posted » : les plus gros mouvements, estimés d'après le nombre d'enchères d'un scan à l'autre.
SORTS = ("name", "price", "listed", "up", "down", "sold", "posted")
MOVEMENT_SORTS = ("sold", "posted")


class AuctionError(ValueError):
    """Scan refusé, avec un message lisible par le joueur."""


class DuplicateScan(AuctionError):
    pass


class PartialScan(DuplicateScan):
    """Bien moins d'objets que le dernier scan de l'hôtel : ce n'est pas un scan complet. Pour le compagnon,
    comme un scan déjà reçu : il le retient et ne le renvoie pas."""


class TooCloseScan(DuplicateScan):
    """Un autre scan du même hôtel existe à moins de `MIN_GAP` : pour le compagnon, c'est un scan déjà reçu
    (il le retient et ne le renvoie pas)."""


def canonical_house(house: Any) -> str:
    """Le nom sous lequel le site range un hôtel. Tout nom qui contient « pvp », quelle que soit la casse, est
    le même hôtel : `PVP_HOUSE`. Les autres gardent leur nom, espaces resserrés. Vide si illisible."""
    house = " ".join(house.split()) if isinstance(house, str) else ""
    return PVP_HOUSE if "pvp" in house.lower() else house


def can_upload(user) -> bool:
    """Qui peut envoyer et lire les prix : tout membre connecté."""
    return bool(user and user.is_authenticated)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _rows(raw: Any) -> dict[int, tuple[int, int | None]]:
    if not isinstance(raw, list) or not raw:
        raise AuctionError("Le scan ne contient aucun objet.")
    if len(raw) > MAX_ITEMS:
        raise AuctionError(f"Le scan contient trop d'objets ({len(raw)}, {MAX_ITEMS} au plus).")
    rows: dict[int, tuple[int, int | None]] = {}
    for entry in raw:
        if not isinstance(entry, list) or not 2 <= len(entry) <= 3:
            raise AuctionError("Chaque objet du scan est une liste [objet, prix, enchères].")
        item_id, price = _int(entry[0]), _int(entry[1])
        if not item_id or not 0 < item_id < 2**31 or not price or not 0 < price <= MAX_PRICE:
            raise AuctionError("Le scan contient un objet ou un prix invalide.")
        listed = None
        if len(entry) == 3 and entry[2] is not None:  # absent ou null : nombre inconnu
            listed = _int(entry[2])
            if listed is None or not 0 <= listed <= MAX_LISTED:
                raise AuctionError("Le scan contient un nombre d'enchères invalide.")
        rows[item_id] = (price, listed)
    return rows


def store_scan(
    user, house: Any, scanned_at: Any, items: Any, *, device: CompanionDevice | None = None
) -> AuctionScan:
    """Enregistre un scan. `DuplicateScan` si cet hôtel a déjà un scan à cet instant, `TooCloseScan` s'il en a
    un à moins de `MIN_GAP` (avant ou après : les scans n'arrivent pas forcément dans l'ordre), `PartialScan`
    s'il compte bien moins d'objets que le dernier scan de l'hôtel."""
    house = canonical_house(house)
    if not house or len(house) > 96:
        raise AuctionError("Hôtel des ventes manquant ou trop long.")
    stamp = _int(scanned_at)
    if not stamp or stamp <= 0:
        raise AuctionError("Date du scan manquante.")
    try:
        when = datetime.fromtimestamp(stamp, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise AuctionError("Date du scan illisible.") from exc
    if when > timezone.now() + timedelta(days=1):
        raise AuctionError("Le scan est daté dans le futur.")
    rows = _rows(items)
    last = AuctionScan.objects.filter(house=house).order_by("-scanned_at").first()
    if last and last.items >= PARTIAL_FLOOR and len(rows) < PARTIAL_SHARE * last.items:
        raise PartialScan(
            f"Scan partiel : {len(rows)} objets, le dernier scan de cet hôtel en compte {last.items}."
        )
    near = AuctionScan.objects.filter(
        house=house, scanned_at__gt=when - MIN_GAP, scanned_at__lt=when + MIN_GAP
    ).exclude(scanned_at=when)
    if near.exists():
        minutes = int(MIN_GAP.total_seconds() // 60)
        raise TooCloseScan(f"Un scan de cet hôtel fait à moins de {minutes} minutes a déjà été reçu.")
    try:
        with transaction.atomic():
            scan = AuctionScan.objects.create(
                house=house, scanned_at=when, user=user, device=device, items=len(rows)
            )
            AuctionPrice.objects.bulk_create(
                [
                    AuctionPrice(scan=scan, item_id=item_id, price=price, listed=listed)
                    for item_id, (price, listed) in rows.items()
                ],
                batch_size=2000,
            )
    except IntegrityError as exc:
        raise DuplicateScan("Ce scan a déjà été reçu.") from exc
    prune(house)
    try:
        check_alerts(scan, rows)
    except Exception:  # noqa: BLE001 — le scan est enregistré : une alerte ratée ne le fait pas renvoyer
        logger.exception("Alertes de prix du scan %s non envoyées", scan.pk)
    return scan


def check_alerts(scan: AuctionScan, rows: dict[int, tuple[int, int | None]]) -> int:
    """Prévient chaque joueur dont un objet suivi vient de franchir un seuil : un MP par joueur, pour les
    seuils franchis à ce scan et pas au précédent regardé (`buy_hit`, `sell_hit`). Un objet sans enchère n'a
    pas de prix : ses seuils se réarment. Seul un scan récent (`ALERT_FRESH`) et le plus récent de son hôtel
    compte : un vieux scan arrivé en retard ne dit rien du prix du moment. Renvoie le nombre de MP mis en
    file."""
    from apps.notifications import services as notify

    if scan.scanned_at < timezone.now() - ALERT_FRESH:
        return 0
    if AuctionScan.objects.filter(house=scan.house, scanned_at__gt=scan.scanned_at).exists():
        return 0
    watched = list(
        FavoriteItem.objects.filter(Q(buy_price__isnull=False) | Q(sell_price__isnull=False))
        .select_related("user")
        .order_by("user_id", "item_id")
    )
    hits: dict[int, list[dict]] = {}
    changed = []
    for favorite in watched:
        price = rows[favorite.item_id][0] if favorite.item_id in rows else None
        buy = price is not None and favorite.buy_price is not None and price <= favorite.buy_price
        sell = price is not None and favorite.sell_price is not None and price >= favorite.sell_price
        for side, now, before, threshold in (
            ("buy", buy, favorite.buy_hit, favorite.buy_price),
            ("sell", sell, favorite.sell_hit, favorite.sell_price),
        ):
            if now and not before:
                hits.setdefault(favorite.user_id, []).append(
                    {"item_id": favorite.item_id, "price": price, "threshold": threshold, "side": side}
                )
        if (buy, sell) != (favorite.buy_hit, favorite.sell_hit):
            favorite.buy_hit, favorite.sell_hit = buy, sell
            changed.append(favorite)
    FavoriteItem.objects.bulk_update(changed, ["buy_hit", "sell_hit"], batch_size=500)
    if not hits:
        return 0
    names = _items({hit["item_id"] for found in hits.values() for hit in found})
    users = {favorite.user_id: favorite.user for favorite in watched}
    sent = 0
    for user_id, found in hits.items():
        for hit in found:
            item = names.get(hit["item_id"])
            hit["name"] = item["name"] if item else f"Objet {hit['item_id']}"
        if notify.auction_alerts(users[user_id], scan.house, scan.scanned_at, found):
            sent += 1
    return sent


def prune(house: str | None = None) -> int:
    """Nettoie un hôtel, ou tous (`None`). Au-delà de KEEP_DAILY, les scans sont supprimés ; entre KEEP_ALL et
    KEEP_DAILY, il n'en reste qu'un par jour (le dernier du jour) : la courbe reste, la table ne grossit plus.
    Renvoie le nombre de scans supprimés."""
    now = timezone.now()
    scans = AuctionScan.objects.all() if house is None else AuctionScan.objects.filter(house=house)
    doomed = list(scans.filter(scanned_at__lt=now - KEEP_DAILY).values_list("pk", flat=True))
    kept_days = set()
    old = scans.filter(scanned_at__lt=now - KEEP_ALL, scanned_at__gte=now - KEEP_DAILY)
    for pk, name, scanned_at in old.order_by("-scanned_at").values_list("pk", "house", "scanned_at"):
        day = (name, timezone.localtime(scanned_at).date())
        if day in kept_days:
            doomed.append(pk)
        else:
            kept_days.add(day)
    if doomed:
        AuctionScan.objects.filter(pk__in=doomed).delete()
    return len(doomed)


def prune_due() -> int:
    """Pour le balayage périodique : nettoie tous les hôtels, une fois par `PRUNE_EVERY` au plus. Sans lui, un
    hôtel que plus personne ne scanne ne serait jamais nettoyé (`store_scan` ne nettoie que le sien)."""
    if not cache.add("gamesync:auctions:prune", 1, PRUNE_EVERY):
        return 0
    return prune()


REPORT_KINDS = (
    "sent", "duplicate", "unchanged", "failed", "unreadable", "no_scan", "stale", "no_file", "not_allowed",
)  # fmt: skip
REPORTS_KEPT = timedelta(days=14)
REPORTS_PER_CALL = 40


def _text(value: Any, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _stamp(value: Any) -> datetime | None:
    stamp = _int(value)
    if not stamp or stamp <= 0:
        return None
    try:
        return datetime.fromtimestamp(stamp, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def store_reports(user, raw: Any, *, device: CompanionDevice | None = None, companion: str = "") -> int:
    """Note ce que le compagnon dit avoir fait de ses fichiers de scan. Un constat identique au dernier du
    même compagnon pour le même addon et le même royaume ne fait pas de nouvelle ligne : son heure et son
    compte avancent. Les lignes de plus de `REPORTS_KEPT` sont supprimées. Renvoie le nombre de constats
    lus."""
    if not isinstance(raw, list):
        raise AuctionError("Rapports illisibles.")
    now = timezone.now()
    read = 0
    for item in raw[:REPORTS_PER_CALL]:
        if not isinstance(item, dict):
            continue
        source, kind = _text(item.get("source"), 32), _text(item.get("kind"), 24)
        if not source or kind not in REPORT_KINDS:
            continue
        read += 1
        items = _int(item.get("items"))
        fields = {
            "kind": kind,
            "detail": _text(item.get("detail"), 600),
            "day": _int(item.get("day")),
            "items": items if items is not None and 0 <= items < 2**31 else None,
            "scanned_at": _stamp(item.get("scanned_at")),
            "file_at": _stamp(item.get("file_at")),
        }
        if fields["day"] is not None and not -(2**31) <= fields["day"] < 2**31:
            fields["day"] = None
        mine = {"user": user, "device": device, "source": source, "house": _text(item.get("house"), 96)}
        last = AuctionReport.objects.filter(**mine).order_by("-at", "-pk").first()
        if last and all(getattr(last, name) == value for name, value in fields.items()):
            last.at, last.count, last.companion = now, last.count + 1, companion[:24]
            last.save(update_fields=["at", "count", "companion"])
        else:
            AuctionReport.objects.create(**mine, **fields, at=now, companion=companion[:24])
    AuctionReport.objects.filter(at__lt=now - REPORTS_KEPT).delete()
    return read


def reports(limit: int = 150) -> list[dict]:
    """Les constats des compagnons, le plus récent d'abord (GM)."""
    rows = AuctionReport.objects.select_related("user", "device").order_by("-at", "-pk")[:limit]
    return [
        {
            "id": r.pk,
            "at": r.at,
            "first_at": r.first_at,
            "count": r.count,
            "user": r.user.display_name,
            "device": r.device.name if r.device else None,
            "companion": r.companion,
            "source": r.source,
            "house": r.house,
            "kind": r.kind,
            "detail": r.detail,
            "day": r.day,
            "items": r.items,
            "scanned_at": r.scanned_at,
            "file_at": r.file_at,
        }
        for r in rows
    ]


def scan_summary(scan: AuctionScan) -> dict:
    return {"id": scan.pk, "house": scan.house, "scanned_at": scan.scanned_at, "items": scan.items}


def houses() -> list[dict]:
    """Les hôtels des ventes connus, le plus récemment scanné d'abord."""
    found: dict[str, dict] = {}
    for house, scanned_at in AuctionScan.objects.order_by("-scanned_at").values_list("house", "scanned_at"):
        entry = found.setdefault(house, {"house": house, "scans": 0, "last_scan": scanned_at})
        entry["scans"] += 1
        entry["first_scan"] = scanned_at
    return list(found.values())


def _baseline(latest: AuctionScan, since: str) -> AuctionScan | None:
    older = AuctionScan.objects.filter(house=latest.house, scanned_at__lt=latest.scanned_at)
    delta = BASELINES.get(since)
    if delta is not None:
        older = older.filter(scanned_at__lte=latest.scanned_at - delta)
    return older.order_by("-scanned_at").first()


def _prices(scan: AuctionScan) -> dict[int, tuple[int, int | None]]:
    return {
        item_id: (price, listed)
        for item_id, price, listed in scan.prices.values_list("item_id", "price", "listed")
    }


def _items(ids) -> dict[int, dict]:
    ids, found = list(ids), {}
    for start in range(0, len(ids), ID_BATCH):
        batch = Item.objects.filter(id__in=ids[start : start + ID_BATCH])
        fields = ("id", "name", "name_en", "quality", "icon", "class_id", "subclass_id", "inventory_type")
        for item in batch.values(*fields):
            found[item["id"]] = item
    return found


def _fold(text: str) -> str:
    """Minuscules sans accents ni ligatures, pour la recherche : « etoffe » trouve « Étoffe »."""
    text = text.lower().replace("œ", "oe").replace("æ", "ae").replace("’", "'")
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def _movement(price: int, listed: int | None, previous: tuple[int, int | None] | None) -> dict:
    """Mouvement d'un objet entre le scan de référence et le dernier, d'après le nombre d'enchères : c'est une
    estimation. Une enchère disparue a pu être vendue, annulée ou avoir expiré, et le scan ne compte que des
    enchères, pas des quantités. `moved` : valeur en cuivre, une unité par enchère au prix le plus bas (celui
    de référence pour des enchères parties, le prix actuel pour des enchères arrivées)."""
    previous_listed = previous[1] if previous else None
    if listed is None or previous_listed is None:
        return {"previous_listed": previous_listed, "listed_change": None, "moved": None}
    delta = listed - previous_listed
    unit = previous[0] if delta < 0 else price
    return {"previous_listed": previous_listed, "listed_change": delta, "moved": abs(delta) * unit}


# Les comparaisons gardées : (dernier scan, référence) → (échéance, lignes, disparus). Dans la mémoire du
# processus et non dans le cache de Django : celui-ci recopie la valeur à chaque lecture (6 000 lignes, 6 Mo
# et 5 ms par requête, sur un serveur de 2 Go). Les lignes sont donc partagées entre les requêtes : à lire
# seulement.
_COMPARED: dict[tuple[int, int], tuple[float, list[dict], list[dict]]] = {}


def forget_comparisons() -> None:
    """Oublie les comparaisons gardées (tests : les identifiants de scan y sont réutilisés)."""
    _COMPARED.clear()


def _compared(latest: AuctionScan, baseline: AuctionScan | None) -> tuple[list[dict], list[dict]]:
    """Chaque objet du dernier scan avec son prix de référence, par nom ; puis les objets du scan de référence
    absents du dernier (plus aucune enchère), montrés par les seuls tris de mouvements. Gardé `ROWS_TTL` :
    filtrer, trier ou changer de page ne relit pas les deux scans. Les listes rendues sont partagées :
    l'appelant ne les modifie pas, ni leurs lignes."""
    key = (latest.pk, baseline.pk if baseline else 0)
    kept = _COMPARED.get(key)
    if kept is not None and kept[0] > time.monotonic():
        return kept[1], kept[2]
    current = _prices(latest)
    before = _prices(baseline) if baseline else {}
    names = _items(current.keys() | before.keys())

    def row(item_id: int, price: int, listed: int | None, previous, gone: bool) -> dict:
        item = names.get(item_id)
        previous_price = previous[0] if previous else None
        return {
            "item_id": item_id,
            "name": item["name"] if item else f"Objet {item_id}",
            "known": item is not None,
            # Ce que la recherche parcourt : le nom français et le nom anglais (le client du jeu peut être
            # dans l'une ou l'autre langue), sans accents. Retiré de la réponse.
            "search": _fold(f"{item['name']}\n{item['name_en']}") if item else "",
            # Ce que le filtre par type lit : classe, sous-classe et emplacement. Retiré de la réponse.
            "kind": (item["class_id"], item["subclass_id"], item["inventory_type"]) if item else None,
            "quality": item["quality"] if item else 1,
            "icon_url": icon_url(item["icon"]) if item else "",
            "price": price,
            "listed": listed,
            "previous_price": previous_price,
            "change": round((price - previous_price) * 100 / previous_price, 1)
            if previous_price and not gone
            else None,
            "gone": gone,
            **_movement(price, listed, previous),
        }

    rows = [
        row(item_id, price, listed, before.get(item_id), False)
        for item_id, (price, listed) in current.items()
    ]
    # Disparus : leur dernier prix connu, zéro enchère.
    gone = [
        row(item_id, previous[0], 0, previous, True)
        for item_id, previous in before.items()
        if item_id not in current
    ]
    rows.sort(key=lambda r: r["name"].lower())
    gone.sort(key=lambda r: r["name"].lower())
    _COMPARED.pop(key, None)
    while len(_COMPARED) >= ROWS_KEPT:  # la plus proche de son échéance s'en va
        del _COMPARED[min(_COMPARED, key=lambda k: _COMPARED[k][0])]
    _COMPARED[key] = (time.monotonic() + ROWS_TTL, rows, gone)
    return rows, gone


def set_favorite_item(user, item_id: int, favorite: bool) -> None:
    """Suit ou ne suit plus un objet. `AuctionError` si l'ID est hors bornes ou si le joueur en suit déjà
    `MAX_FAVORITE_ITEMS`."""
    if not favorite:
        FavoriteItem.objects.filter(user=user, item_id=item_id).delete()
        return
    if not 0 < item_id < 2**31:
        raise AuctionError("Objet inconnu.")
    if FavoriteItem.objects.filter(user=user, item_id=item_id).exists():
        return
    if FavoriteItem.objects.filter(user=user).count() >= MAX_FAVORITE_ITEMS:
        raise AuctionError(f"Tu suis déjà {MAX_FAVORITE_ITEMS} objets : retires-en un d'abord.")
    FavoriteItem.objects.get_or_create(user=user, item_id=item_id)


def _threshold(value: Any) -> int | None:
    if value is None:
        return None
    price = _int(value)
    if price is None or not 0 < price <= MAX_PRICE:
        raise AuctionError("Prix invalide : un nombre de cuivres, plus grand que zéro.")
    return price


def set_item_alerts(user, item_id: int, buy_price: Any, sell_price: Any) -> None:
    """Pose les deux seuils d'un objet, en cuivre (`None` : pas de seuil) ; l'objet est suivi s'il ne l'était
    pas. Un seuil qui change se réarme : le prochain scan qui le franchit prévient, même si le prix y était
    déjà. `AuctionError` si un prix est illisible, si le prix d'achat n'est pas sous le prix de vente, ou si
    le joueur suit déjà `MAX_FAVORITE_ITEMS` objets."""
    buy, sell = _threshold(buy_price), _threshold(sell_price)
    if buy is not None and sell is not None and buy >= sell:
        raise AuctionError("Le prix d'achat doit être plus bas que le prix de vente.")
    set_favorite_item(user, item_id, True)
    favorite = FavoriteItem.objects.get(user=user, item_id=item_id)
    if favorite.buy_price != buy:
        favorite.buy_price, favorite.buy_hit = buy, False
    if favorite.sell_price != sell:
        favorite.sell_price, favorite.sell_hit = sell, False
    favorite.save(update_fields=["buy_price", "sell_price", "buy_hit", "sell_hit"])


def overview(
    house: str = "",
    q: str = "",
    sort: str = "name",
    since: str = "prev",
    page: int = 1,
    category: str = "",
    user=None,
    favorites: bool = False,
) -> dict:
    """Le dernier scan d'un hôtel, comparé à un scan de référence : une page d'objets filtrés et triés.
    `category` : clé d'un type d'objet (`auction_categories`), ignorée si elle n'en nomme aucun. Un objet
    absent de l'index du site n'est d'aucun type. `user` : chaque objet dit s'il le suit (`favorite`) et
    avec quels seuils (`buy_price`, `sell_price`) ; `favorites` : seuls ses objets suivis, ceux qui n'ont
    plus d'enchère compris (leur dernier prix connu au scan de référence, `gone`)."""
    followed: dict[int, tuple[int | None, int | None]] = {}
    if user is not None and getattr(user, "is_authenticated", False):
        followed = {
            item_id: (buy, sell)
            for item_id, buy, sell in FavoriteItem.objects.filter(user=user).values_list(
                "item_id", "buy_price", "sell_price"
            )
        }
    known = houses()
    in_category = auction_categories.test_for(category)
    category = category if in_category else ""
    shared = {"categories": auction_categories.tree(), "category": category, "favorites": len(followed)}
    house = canonical_house(house)
    sort = sort if sort in SORTS else "name"
    since = since if since in BASELINES else "prev"
    empty = {
        "houses": known, "house": "", "scan": None, "baseline": None, "since": since, "sort": sort,
        "total": 0, "page": 1, "pages": 1, "results": [], **shared,
    }  # fmt: skip
    if not known:
        return empty
    house = house if any(h["house"] == house for h in known) else known[0]["house"]
    latest = AuctionScan.objects.filter(house=house).order_by("-scanned_at").first()
    if latest is None:
        return empty
    baseline = _baseline(latest, since)
    rows, gone = _compared(latest, baseline)
    if sort in MOVEMENT_SORTS:
        rows = rows + gone
    if favorites:
        # Un favori sans enchère reste dans la liste : c'est justement lui qu'on guette.
        pool = rows if sort in MOVEMENT_SORTS else rows + gone
        rows = [r for r in pool if r["item_id"] in followed]
        if sort == "name":
            rows.sort(key=lambda r: r["name"].lower())

    if in_category:
        rows = [r for r in rows if r["kind"] is not None and in_category(r["kind"])]
    needle = _fold(" ".join(q.split()))
    if needle:
        rows = [r for r in rows if needle in r["search"] or needle == str(r["item_id"])]
    if sort == "price":
        rows = sorted(rows, key=lambda r: (-r["price"], r["name"]))
    elif sort == "listed":
        rows = sorted(rows, key=lambda r: (-(r["listed"] or 0), r["name"]))
    elif sort in ("up", "down"):
        # Les objets sans prix de référence n'ont pas de variation : ils sortent de ces deux tris.
        rows = [r for r in rows if r["change"] is not None]
        rows.sort(key=lambda r: (-r["change"] if sort == "up" else r["change"], r["name"]))
    elif sort in MOVEMENT_SORTS:
        # Enchères parties (« sold ») ou arrivées (« posted »), les plus grosses valeurs estimées d'abord.
        sign = -1 if sort == "sold" else 1
        rows = [r for r in rows if r["listed_change"] is not None and r["listed_change"] * sign > 0]
        rows.sort(key=lambda r: (-r["moved"], -abs(r["listed_change"]), r["name"]))
    # sinon : par nom, l'ordre du cache

    pages = max(1, -(-len(rows) // PAGE_SIZE))
    page = min(max(1, page), pages)
    return {
        "houses": known,
        "house": house,
        "scan": scan_summary(latest),
        "baseline": scan_summary(baseline) if baseline else None,
        "since": since,
        "sort": sort,
        "total": len(rows),
        "page": page,
        "pages": pages,
        "results": [
            {
                **{k: v for k, v in r.items() if k not in ("search", "kind")},
                "favorite": r["item_id"] in followed,
                "buy_price": followed.get(r["item_id"], (None, None))[0],
                "sell_price": followed.get(r["item_id"], (None, None))[1],
            }
            for r in rows[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        ],
        **shared,
    }


def item_history(item_id: int, house: str = "") -> dict:
    """Le prix et le nombre d'enchères d'un objet à chaque scan d'un hôtel, du plus ancien au plus récent,
    avec le nom affiché du membre qui a envoyé le scan."""
    known = houses()
    house = canonical_house(house)
    if known and not any(h["house"] == house for h in known):
        house = known[0]["house"]
    points = list(
        AuctionPrice.objects.filter(item_id=item_id, scan__house=house)
        .order_by("-scan__scanned_at")
        .values_list("scan__scanned_at", "price", "listed", "scan__user__display_name")[:HISTORY_POINTS]
    )
    points.reverse()
    item = Item.objects.filter(id=item_id).values("name", "quality", "icon").first()
    prices = [price for _, price, _, _ in points]
    return {
        "item_id": item_id,
        "house": house,
        "name": item["name"] if item else f"Objet {item_id}",
        "quality": item["quality"] if item else 1,
        "icon_url": icon_url(item["icon"]) if item else "",
        "min": min(prices) if prices else None,
        "max": max(prices) if prices else None,
        "average": round(sum(prices) / len(prices)) if prices else None,
        "points": [
            {"at": at, "price": price, "listed": listed, "by": by} for at, price, listed, by in points
        ],
    }


def _latest_scan(house: str) -> AuctionScan | None:
    """Le dernier scan de l'hôtel demandé, ou du plus récemment scanné s'il est inconnu."""
    scans = AuctionScan.objects.order_by("-scanned_at")
    return scans.filter(house=canonical_house(house)).first() or scans.first()


def set_favorite(user, recipe_id: int, favorite: bool) -> None:
    """Suit ou ne suit plus une recette. `AuctionError` si la recette n'existe pas."""
    if not favorite:
        FavoriteRecipe.objects.filter(user=user, recipe_id=recipe_id).delete()
        return
    if not Recipe.objects.filter(pk=recipe_id).exists():
        raise AuctionError("Recette inconnue.")
    FavoriteRecipe.objects.get_or_create(user=user, recipe_id=recipe_id)


def _reagents(recipe: Recipe) -> list[tuple[int, str, int]]:
    """Les composants lisibles d'une recette : (objet, nom, nombre)."""
    found = []
    for entry in recipe.reagents if isinstance(recipe.reagents, list) else []:
        if not isinstance(entry, dict):
            continue
        item_id, count = _int(entry.get("item_id")), _int(entry.get("count"))
        if item_id and count and count > 0:
            found.append((item_id, str(entry.get("name") or ""), count))
    return found


def _recipe_row(recipe: Recipe, favorite: bool, prices: dict, items: dict) -> dict:
    def item_part(item_id: int, fallback: str) -> dict:
        item = items.get(item_id)
        price = prices.get(item_id)
        return {
            "item_id": item_id,
            "name": item["name"] if item else fallback or f"Objet {item_id}",
            "quality": item["quality"] if item else 1,
            "icon_url": icon_url(item["icon"]) if item else "",
            "price": price[0] if price else None,
            "listed": price[1] if price else None,
        }

    reagents, cost, missing = [], 0, 0
    for item_id, name, count in _reagents(recipe):
        part = item_part(item_id, name)
        part["count"] = count
        part["total"] = part["price"] * count if part["price"] is not None else None
        if part["total"] is None:
            missing += 1
        else:
            cost += part["total"]
        reagents.append(part)
    priced = len(reagents) - missing

    product = item_part(recipe.product_id, "") if recipe.product_id else None
    revenue = product["price"] * recipe.quantity if product and product["price"] is not None else None
    # Le bénéfice ne compte que les composants en vente : `missing` dit combien manquent au calcul.
    profit = revenue - cost if revenue is not None and priced else None
    return {
        "recipe_id": recipe.pk,
        "name": recipe.name,
        "icon_url": icon_url(recipe.icon),
        "profession": recipe.profession.name,
        "min_skill": recipe.min_skill,
        "quantity": recipe.quantity,
        "favorite": favorite,
        "product": product,
        "reagents": reagents,
        "cost": cost if priced else None,
        "missing": missing,
        "revenue": revenue,
        "profit": profit,
        "margin": round(profit * 100 / cost, 1) if profit is not None and cost else None,
    }


def recipe_costs(user, house: str = "", q: str = "") -> dict:
    """Les recettes favorites du joueur, ou celles que trouve `q` (deux lettres au moins), chacune avec le
    coût de ses composants et le prix de son produit au dernier scan de l'hôtel."""
    latest = _latest_scan(house)
    favorites = set(FavoriteRecipe.objects.filter(user=user).values_list("recipe_id", flat=True))
    recipes = Recipe.objects.select_related("profession")
    needle = q.strip()
    searching = len(needle) >= 2
    if searching:
        recipes = recipes.filter(
            Q(name__icontains=needle)
            | Q(product__name__icontains=needle)
            | Q(product__name_en__icontains=needle)
        ).order_by("name")[:RECIPE_RESULTS]
    else:
        recipes = recipes.filter(pk__in=favorites).order_by("name")
    recipes = list(recipes)

    wanted = {item_id for recipe in recipes for item_id, _, _ in _reagents(recipe)}
    wanted.update(recipe.product_id for recipe in recipes if recipe.product_id)
    prices: dict[int, tuple[int, int | None]] = {}
    if latest and wanted:
        found = AuctionPrice.objects.filter(scan=latest, item_id__in=wanted)
        prices = {
            item_id: (price, listed)
            for item_id, price, listed in found.values_list("item_id", "price", "listed")
        }
    items = _items(wanted)
    return {
        "house": latest.house if latest else "",
        "scan": scan_summary(latest) if latest else None,
        "searching": searching,
        "favorites": len(favorites),
        "results": [_recipe_row(recipe, recipe.pk in favorites, prices, items) for recipe in recipes],
    }
