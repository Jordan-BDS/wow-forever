"""
Prix de l'hôtel des ventes : le compagnon du GM envoie chaque scan complet lu dans le fichier de l'addon de
scan, le site les garde tous et en tire l'historique de chaque objet. Envoi et lecture réservés au GM.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.gamedata.models import Item, Recipe
from apps.gamedata.stats import icon_url

from .models import AuctionPrice, AuctionScan, CompanionDevice, FavoriteRecipe

MAX_ITEMS = 60_000
RECIPE_RESULTS = 30  # recettes montrées par une recherche
MAX_PRICE = 10**12
MAX_LISTED = 10**7
PAGE_SIZE = 100
HISTORY_POINTS = 500
KEEP_ALL = timedelta(days=30)  # tous les scans sont gardés ce temps-là, puis un par jour
ROWS_TTL = (
    300  # s : la comparaison de deux scans (immuables) est gardée en cache, seuls les noms peuvent bouger
)
ID_BATCH = 5000  # objets par requête sur l'index (SQLite borne le nombre de paramètres)

# Référence de la variation : le scan précédent, ou le dernier scan vieux d'au moins un jour / une semaine.
BASELINES = {"prev": None, "day": timedelta(days=1), "week": timedelta(days=7)}
# « sold » et « posted » : les plus gros mouvements, estimés d'après le nombre d'enchères d'un scan à l'autre.
SORTS = ("name", "price", "listed", "up", "down", "sold", "posted")
MOVEMENT_SORTS = ("sold", "posted")


class AuctionError(ValueError):
    """Scan refusé, avec un message lisible par le joueur."""


class DuplicateScan(AuctionError):
    pass


def can_upload(user) -> bool:
    """Qui peut envoyer et lire les prix : le GM seulement, pour l'instant."""
    return bool(user and user.is_authenticated and user.is_gm)


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
    """Enregistre un scan. `DuplicateScan` si cet hôtel a déjà un scan à cet instant."""
    house = " ".join(house.split()) if isinstance(house, str) else ""
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
    return scan


def prune(house: str) -> int:
    """Au-delà de KEEP_ALL, un hôtel ne garde qu'un scan par jour (le dernier du jour) : la courbe reste, la
    table ne grossit plus de chaque scan. Renvoie le nombre de scans supprimés."""
    kept_days, doomed = set(), []
    old = AuctionScan.objects.filter(house=house, scanned_at__lt=timezone.now() - KEEP_ALL)
    for pk, scanned_at in old.order_by("-scanned_at").values_list("pk", "scanned_at"):
        day = timezone.localtime(scanned_at).date()
        if day in kept_days:
            doomed.append(pk)
        else:
            kept_days.add(day)
    if doomed:
        AuctionScan.objects.filter(pk__in=doomed).delete()
    return len(doomed)


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
        for item in batch.values("id", "name", "quality", "icon"):
            found[item["id"]] = item
    return found


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


def _compared(latest: AuctionScan, baseline: AuctionScan | None) -> tuple[list[dict], list[dict]]:
    """Chaque objet du dernier scan avec son prix de référence, par nom ; puis les objets du scan de référence
    absents du dernier (plus aucune enchère), montrés par les seuls tris de mouvements. Gardé en cache :
    filtrer, trier ou changer de page ne relit pas les deux scans."""
    key = f"gamesync:auctions:2:{latest.pk}:{baseline.pk if baseline else 0}"
    cached = cache.get(key)
    if cached is not None:
        return cached
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
    cache.set(key, (rows, gone), ROWS_TTL)
    return rows, gone


def overview(house: str = "", q: str = "", sort: str = "name", since: str = "prev", page: int = 1) -> dict:
    """Le dernier scan d'un hôtel, comparé à un scan de référence : une page d'objets filtrés et triés."""
    known = houses()
    sort = sort if sort in SORTS else "name"
    since = since if since in BASELINES else "prev"
    empty = {
        "houses": known, "house": "", "scan": None, "baseline": None, "since": since, "sort": sort,
        "total": 0, "page": 1, "pages": 1, "results": [],
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

    needle = q.strip().lower()
    if needle:
        rows = [r for r in rows if needle in r["name"].lower() or needle == str(r["item_id"])]
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
        "results": rows[(page - 1) * PAGE_SIZE : page * PAGE_SIZE],
    }


def item_history(item_id: int, house: str = "") -> dict:
    """Le prix et le nombre d'enchères d'un objet à chaque scan d'un hôtel, du plus ancien au plus récent."""
    known = houses()
    if known and not any(h["house"] == house for h in known):
        house = known[0]["house"]
    points = list(
        AuctionPrice.objects.filter(item_id=item_id, scan__house=house)
        .order_by("-scan__scanned_at")
        .values_list("scan__scanned_at", "price", "listed")[:HISTORY_POINTS]
    )
    points.reverse()
    item = Item.objects.filter(id=item_id).values("name", "quality", "icon").first()
    prices = [price for _, price, _ in points]
    return {
        "item_id": item_id,
        "house": house,
        "name": item["name"] if item else f"Objet {item_id}",
        "quality": item["quality"] if item else 1,
        "icon_url": icon_url(item["icon"]) if item else "",
        "min": min(prices) if prices else None,
        "max": max(prices) if prices else None,
        "average": round(sum(prices) / len(prices)) if prices else None,
        "points": [{"at": at, "price": price, "listed": listed} for at, price, listed in points],
    }


def _latest_scan(house: str) -> AuctionScan | None:
    """Le dernier scan de l'hôtel demandé, ou du plus récemment scanné s'il est inconnu."""
    scans = AuctionScan.objects.order_by("-scanned_at")
    return scans.filter(house=house).first() or scans.first()


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
