"""
Primes posées à la main : un membre met tant d'or (et, s'il veut, des objets) par kill sur un joueur adverse,
pour un nombre de kills au plus. Le site compte les kills et tient le registre de qui doit quoi à qui.

Les kills ne sont pas stockés : comme le Wanted, ils sont relus dans les événements `pk` que l'addon exporte
(kill de joueur, hors champ de bataille). Un kill compte pour une prime s'il nomme sa cible (nom exact, ou
prénom seul d'un côté ou de l'autre), entre la pose de la prime et son annulation. Les `pk` d'une même cible
à moins de `KILL_DEDUPE_SECONDS` sont un seul kill fait à plusieurs : la prime du kill est partagée entre
ses chasseurs, un joueur comptant une fois quel que soit son nombre de personnages. Le commanditaire ne se
doit rien : sa part n'est due à personne, et un kill qu'il fait seul ne consomme pas la prime. Seuls les
`max_kills` premiers kills sont payés.

Le paiement se fait en jeu, le site ne le voit pas : le commanditaire déclare ce qu'il a remis
(`BountyPayment`). Le reste dû à un chasseur est ce que ses kills lui valent, moins ce qui a été déclaré.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.characters.models import Character
from apps.gamedata.models import Item
from apps.gamedata.stats import icon_url

from .models import Bounty, BountyPayment
from .progress import latest_snapshots, number
from .wanted import KILL_DEDUPE_SECONDS, _who, key_of

COPPER = 10_000  # cuivres dans une pièce d'or
MAX_GOLD = 100_000  # po par kill
MAX_KILLS = 100
MAX_ITEMS = 1000  # objets par kill
KILLS_TTL = 60  # s : les kills lus dans les exports sont gardés en cache, comme la page Wanted
KILLS_CACHE = "gamesync:bounties:kills"
COMPANION_DAYS = (
    60  # une prime finie ou annulée est encore dite au compagnon ce temps-là, pour que l'addon la ferme
)
COMPANION_LIMIT = 100  # Data.BOUNTY_MAX de l'addon


class BountyError(ValueError):
    """Demande refusée, avec un message lisible par le joueur."""


def names_match(target: str, name: str) -> bool:
    """La cible d'une prime et le nom lu par l'addon désignent le même joueur : même nom, ou le prénom seul
    d'un côté (le message de victoire honorable peut ne donner que le prénom)."""
    if target == name:
        return True
    a, b = target.split(" "), name.split(" ")
    return (len(a) == 1 or len(b) == 1) and a[0] == b[0] and a[0] != ""


def split(total: int, parts: int) -> list[int]:
    """`total` partagé en `parts` parts entières : le reste va aux premières."""
    if parts <= 0:
        return []
    base, rest = divmod(total, parts)
    return [base + (1 if i < rest else 0) for i in range(parts)]


def player_kills() -> list[dict]:
    """Chaque kill de joueur exporté par l'addon, hors champ de bataille, du plus ancien au plus récent :
    { key, t, zone, who }. Un kill fait à plusieurs y est autant de fois que de chasseurs."""
    cached = cache.get(KILLS_CACHE)
    if cached is not None:
        return cached
    kills = []
    for snapshot in latest_snapshots().values():
        data = snapshot.data if isinstance(snapshot.data, dict) else {}
        who = _who(snapshot.character)
        for event in data.get("events") or []:
            if not isinstance(event, dict) or event.get("k") != "pk" or event.get("bg") is True:
                continue
            key = key_of(event.get("name")) if isinstance(event.get("name"), str) else ""
            if key:
                kills.append(
                    {
                        "key": key,
                        "t": number(event.get("t")),
                        "zone": str(event.get("zone") or ""),
                        "who": who,
                    }
                )
    kills.sort(key=lambda k: k["t"])
    cache.set(KILLS_CACHE, kills, KILLS_TTL)
    return kills


def bounty_kills(bounty: Bounty, kills: list[dict]) -> list[dict]:
    """Les kills payés par une prime, du plus ancien au plus récent : { t, zone, hunters }, chaque chasseur
    avec sa part { who, amount, items }. Le commanditaire n'est pas un chasseur de sa propre prime."""
    start = bounty.created_at.timestamp()
    end = bounty.cancelled_at.timestamp() if bounty.cancelled_at else float("inf")
    found: list[dict] = []
    for kill in kills:
        if not start <= kill["t"] <= end or not names_match(bounty.target_key, kill["key"]):
            continue
        if kill["who"]["user"]["id"] == bounty.poster_id:
            continue
        same = found[-1] if found and kill["t"] - found[-1]["t"] < KILL_DEDUPE_SECONDS else None
        if same is None:
            if len(found) >= bounty.max_kills:
                break
            same = {"t": kill["t"], "zone": kill["zone"], "hunters": {}}
            found.append(same)
        same["hunters"].setdefault(kill["who"]["user"]["id"], kill["who"])
        same["zone"] = same["zone"] or kill["zone"]
    for kill in found:
        hunters = list(kill["hunters"].values())
        gold = split(bounty.amount, len(hunters))
        items = split(bounty.item_count if bounty.item_id else 0, len(hunters))
        kill["hunters"] = [
            {"who": who, "amount": gold[i], "items": items[i]} for i, who in enumerate(hunters)
        ]
    return found


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=UTC).isoformat()


def _user(user) -> dict:
    return {"id": user.pk, "display_name": user.display_name}


def _item(item: Item | None) -> dict | None:
    if item is None:
        return None
    return {"id": item.pk, "name": item.name, "quality": item.quality, "icon_url": icon_url(item.icon)}


def can_cancel(user, bounty: Bounty) -> bool:
    return bounty.cancelled_at is None and (user.pk == bounty.poster_id or user.is_officer_or_above)


def can_pay(user, bounty: Bounty) -> bool:
    return user.pk == bounty.poster_id or user.is_gm


def _dues(bounty: Bounty, kills: list[dict]) -> list[dict]:
    """Par chasseur : ce que ses kills lui valent, ce qui a été déclaré payé, ce qui reste dû."""
    dues: dict[int, dict] = {}
    for kill in kills:
        for share in kill["hunters"]:
            user = share["who"]["user"]
            due = dues.setdefault(
                user["id"], {"hunter": user, "kills": 0, "amount": 0, "items": 0, "paid": 0, "items_paid": 0}
            )
            due["kills"] += 1
            due["amount"] += share["amount"]
            due["items"] += share["items"]
    for payment in bounty.payments.all():
        # Un paiement à quelqu'un qui n'a plus de kill (export corrigé depuis) reste dans les comptes.
        due = dues.setdefault(
            payment.hunter_id,
            {
                "hunter": _user(payment.hunter),
                "kills": 0,
                "amount": 0,
                "items": 0,
                "paid": 0,
                "items_paid": 0,
            },
        )
        due["paid"] += payment.amount
        due["items_paid"] += payment.item_count
    for due in dues.values():
        due["owed"] = max(0, due["amount"] - due["paid"])
        due["items_owed"] = max(0, due["items"] - due["items_paid"])
    return sorted(dues.values(), key=lambda d: (-d["owed"], -d["items_owed"], d["hunter"]["display_name"]))


def _serialize(bounty: Bounty, kills: list[dict], user) -> dict:
    paid_kills = bounty_kills(bounty, kills)
    status = "cancelled" if bounty.cancelled_at else "done" if len(paid_kills) >= bounty.max_kills else "open"
    return {
        "id": bounty.pk,
        "target": bounty.target_name,
        "poster": _user(bounty.poster),
        "amount": bounty.amount,
        "item": _item(bounty.item),
        "item_count": bounty.item_count if bounty.item_id else 0,
        "max_kills": bounty.max_kills,
        "note": bounty.note,
        "created_at": bounty.created_at,
        "cancelled_at": bounty.cancelled_at,
        "status": status,
        "kills": [
            {
                "at": _iso(kill["t"]),
                "zone": kill["zone"],
                "hunters": [
                    {**share["who"], "amount": share["amount"], "items": share["items"]}
                    for share in kill["hunters"]
                ],
            }
            for kill in reversed(paid_kills)
        ],
        "dues": _dues(bounty, paid_kills),
        "can_cancel": can_cancel(user, bounty),
        "can_pay": can_pay(user, bounty),
    }


def _ledger(bounties: list[dict]) -> list[dict]:
    """Qui doit quoi à qui, toutes primes confondues : l'or en un montant, les objets par objet."""
    ledger: dict[tuple[int, int], dict] = {}
    for bounty in bounties:
        for due in bounty["dues"]:
            if not due["owed"] and not due["items_owed"]:
                continue
            line = ledger.setdefault(
                (bounty["poster"]["id"], due["hunter"]["id"]),
                {"from": bounty["poster"], "to": due["hunter"], "amount": 0, "items": {}},
            )
            line["amount"] += due["owed"]
            if due["items_owed"] and bounty["item"]:
                item = line["items"].setdefault(bounty["item"]["id"], {**bounty["item"], "count": 0})
                item["count"] += due["items_owed"]
    lines = [{**line, "items": list(line["items"].values())} for line in ledger.values()]
    return sorted(
        lines, key=lambda row: (-row["amount"], row["from"]["display_name"], row["to"]["display_name"])
    )


def report(user) -> dict:
    """La page Primes : chaque prime avec ses kills et ses comptes, puis le registre des dettes."""
    kills = player_kills()
    queryset = Bounty.objects.select_related("poster", "item").prefetch_related("payments__hunter")
    bounties = [_serialize(bounty, kills, user) for bounty in queryset]
    order = {"open": 0, "done": 1, "cancelled": 2}
    bounties.sort(key=lambda b: order[b["status"]])  # tri stable : les plus récentes d'abord dans chaque état
    return {"bounties": bounties, "ledger": _ledger(bounties)}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def import_posted(raw: Any) -> int:
    """Primes posées en jeu (`/mf prime`), lues dans un export : celles du joueur et celles qu'il a reçues de
    guildiens, chacune avec l'identifiant que l'addon lui a donné. Le commanditaire est le propriétaire du
    personnage qui l'a posée : une prime d'un personnage inconnu du site attend l'export de son joueur.
    Une prime déjà connue n'est pas recréée ; son annulation en jeu est reprise. Renvoie le nombre de primes
    créées."""
    created = 0
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        addon_id, guid, name = entry.get("id"), entry.get("guid"), entry.get("name")
        gold, max_kills, posted = (
            _number(entry.get("gold")),
            _number(entry.get("max")),
            _number(entry.get("t")),
        )
        if not (isinstance(addon_id, str) and isinstance(guid, str) and isinstance(name, str)):
            continue
        name = " ".join(name.split())
        if not 1 <= len(addon_id) <= 40 or not guid or not 2 <= len(name) <= 64:
            continue
        if gold is None or max_kills is None or posted is None or posted <= 0:
            continue
        if not 1 <= gold <= MAX_GOLD or not 1 <= max_kills <= MAX_KILLS or gold != int(gold):
            continue
        bounty = Bounty.objects.filter(addon_id=addon_id).first()
        if bounty is None:
            poster = Character.objects.filter(guid=guid).select_related("owner").first()
            if poster is None:
                continue
            try:
                at = min(datetime.fromtimestamp(posted, tz=UTC), timezone.now())
            except (OverflowError, OSError, ValueError):
                continue
            bounty = Bounty.objects.create(
                poster=poster.owner, addon_id=addon_id, target_name=name, amount=int(gold) * COPPER,
                max_kills=int(max_kills), created_at=at,
            )  # fmt: skip
            created += 1
        cancelled = _number(entry.get("cancelled"))
        if cancelled and cancelled > 0 and bounty.cancelled_at is None:
            try:
                at = datetime.fromtimestamp(cancelled, tz=UTC)
            except (OverflowError, OSError, ValueError):
                continue
            bounty.cancelled_at = max(bounty.created_at, min(at, timezone.now()))
            bounty.save(update_fields=["cancelled_at"])
    return created


def companion_bounties() -> list[dict]:
    """Les primes dans les termes de l'addon, que le compagnon recopie dans `db.bounties` jeu fermé : celles
    en cours, et celles finies ou annulées depuis peu (`closed`) pour que l'addon cesse d'alerter.
    Identifiant : celui de l'addon pour une prime posée en jeu, « s » et son numéro pour une prime du site."""
    kills = player_kills()
    recent = timezone.now() - timedelta(days=COMPANION_DAYS)
    out = []
    for bounty in Bounty.objects.select_related("poster", "item")[: COMPANION_LIMIT * 3]:
        counted = len(bounty_kills(bounty, kills))
        closed = bounty.cancelled_at is not None or counted >= bounty.max_kills
        if closed and bounty.created_at < recent:
            continue
        out.append(
            {
                "id": bounty.addon_id or f"s{bounty.pk}",
                "name": bounty.target_name,
                "gold": bounty.amount // COPPER,
                "item": f"{bounty.item_count} × {bounty.item.name}" if bounty.item else None,
                "max": bounty.max_kills,
                "t": int(bounty.created_at.timestamp()),
                "by": bounty.poster.display_name,
                "kills": counted,
                "closed": closed,
            }
        )
        if len(out) >= COMPANION_LIMIT:
            break
    return out


def _whole(value: Any, label: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise BountyError(f"{label} : un nombre entier entre {low} et {high}.")
    return value


def create(user, data: Any) -> Bounty:
    """Pose une prime. `data` : target, gold (po par kill), max_kills, item_id, item_count, note."""
    data = data if isinstance(data, dict) else {}
    target = " ".join(data["target"].split()) if isinstance(data.get("target"), str) else ""
    if not 2 <= len(target) <= 64:
        raise BountyError("Nom de la cible manquant ou trop long.")
    gold = _whole(data.get("gold", 0), "Or par kill", 0, MAX_GOLD)
    max_kills = _whole(data.get("max_kills", 1), "Nombre de kills", 1, MAX_KILLS)
    item, item_count = None, 0
    if data.get("item_id") is not None:
        item = Item.objects.filter(pk=_whole(data["item_id"], "Objet", 1, 2**31 - 1)).first()
        if item is None:
            raise BountyError("Objet inconnu.")
        item_count = _whole(data.get("item_count", 1), "Objets par kill", 1, MAX_ITEMS)
    if not gold and item is None:
        raise BountyError("Une prime offre de l'or, des objets, ou les deux.")
    note = " ".join(data["note"].split())[:200] if isinstance(data.get("note"), str) else ""
    already = Bounty.objects.filter(poster=user, target_key=target.lower(), cancelled_at__isnull=True)
    kills = player_kills()
    if any(len(bounty_kills(bounty, kills)) < bounty.max_kills for bounty in already):
        raise BountyError("Tu as déjà une prime en cours sur ce joueur.")
    return Bounty.objects.create(
        poster=user, target_name=target, amount=gold * COPPER, item=item, item_count=item_count,
        max_kills=max_kills, note=note,
    )  # fmt: skip


def cancel(user, bounty: Bounty) -> None:
    """Annule une prime : les kills faits jusque-là restent dus."""
    if bounty.cancelled_at is not None:
        return
    if not can_cancel(user, bounty):
        raise BountyError("Seul son commanditaire, un officier ou le GM annule une prime.")
    bounty.cancelled_at = timezone.now()
    bounty.save(update_fields=["cancelled_at"])


def pay(user, bounty: Bounty, hunter_id: Any) -> BountyPayment:
    """Déclare payé tout ce que la prime doit encore à un chasseur."""
    if not can_pay(user, bounty):
        raise BountyError("Seul le commanditaire de la prime, ou le GM, déclare un paiement.")
    with transaction.atomic():
        bounty = Bounty.objects.select_for_update().get(pk=bounty.pk)
        dues = _dues(bounty, bounty_kills(bounty, player_kills()))
        due = next((d for d in dues if d["hunter"]["id"] == hunter_id), None)
        if due is None or (not due["owed"] and not due["items_owed"]):
            raise BountyError("Cette prime ne doit rien à ce joueur.")
        return BountyPayment.objects.create(
            bounty=bounty, hunter_id=hunter_id, amount=due["owed"], item_count=due["items_owed"],
            recorded_by=user,
        )  # fmt: skip
