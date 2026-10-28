"""
Lecture des instantanés bruts : état courant d'un personnage, valeur des compteurs à une date, séries pour les
courbes. Tout vient du JSON écrit par l'addon (`CharacterSnapshot.data`), jamais d'une table recalculée.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.characters.models import Character
from apps.gamedata.models import Item

from .models import CharacterSnapshot, ImportBatch, SnapshotStatus
from .services import PARIS

APPLIED = (SnapshotStatus.APPLIED, SnapshotStatus.CREATED)


def latest_snapshot(character: Character) -> CharacterSnapshot | None:
    return (
        CharacterSnapshot.objects.filter(character=character, status__in=APPLIED)
        .order_by("-exported_at")
        .first()
    )


def latest_snapshots() -> dict[int, CharacterSnapshot]:
    """Dernier instantané appliqué de chaque personnage (une requête)."""
    result: dict[int, CharacterSnapshot] = {}
    queryset = (
        CharacterSnapshot.objects.filter(
            status__in=APPLIED, character__isnull=False, character__owner__is_active=True
        )
        .select_related("character__owner", "character__player_class")
        .order_by("-exported_at")
    )
    for snapshot in queryset:
        result.setdefault(snapshot.character_id, snapshot)
    return result


def number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def counter(counters: Any, key: str) -> float:
    """Lit `a.b` dans un dict imbriqué ; tout ce qui n'est pas un nombre vaut 0."""
    node = counters
    for part in key.split("."):
        if not isinstance(node, dict):
            return 0.0
        node = node.get(part)
    return number(node)


def day_of(snapshot: CharacterSnapshot) -> date:
    return snapshot.exported_at.astimezone(PARIS).date()


def counters_at(snapshot: CharacterSnapshot, day: date) -> tuple[dict | None, date | None]:
    """Compteurs cumulés en fin de `day` : l'état courant si `day` est le jour de l'export ou après, sinon la
    dernière entrée du journal à cette date ou avant. Renvoie aussi le jour réellement utilisé."""
    data = snapshot.data if isinstance(snapshot.data, dict) else {}
    if day >= day_of(snapshot):
        return (data.get("counters") if isinstance(data.get("counters"), dict) else {}), day_of(snapshot)
    journal = data.get("journal") if isinstance(data.get("journal"), dict) else {}
    key = day.isoformat()
    candidates = sorted(k for k in journal if isinstance(k, str) and k <= key)
    if not candidates:
        return None, None
    chosen = candidates[-1]
    return (journal[chosen] if isinstance(journal[chosen], dict) else {}), date.fromisoformat(chosen)


def earliest_known(snapshot: CharacterSnapshot) -> tuple[dict, date]:
    """Première valeur connue (plus ancienne entrée du journal, sinon l'état courant)."""
    data = snapshot.data if isinstance(snapshot.data, dict) else {}
    journal = data.get("journal") if isinstance(data.get("journal"), dict) else {}
    keys = sorted(k for k in journal if isinstance(k, str))
    if keys:
        first = keys[0]
        return (journal[first] if isinstance(journal[first], dict) else {}), date.fromisoformat(first)
    return (data.get("counters") if isinstance(data.get("counters"), dict) else {}), day_of(snapshot)


def delta(
    snapshot: CharacterSnapshot, key: str, start: date | None, end_day: date
) -> tuple[float, date | None]:
    """Progression d'un compteur entre la veille de `start` et la fin de `end_day`.

    Sans valeur connue avant `start`, la plus ancienne connue sert de base et son jour est renvoyé
    (« depuis le »)."""
    current, _ = counters_at(snapshot, end_day)
    if current is None:
        return 0.0, None
    if start is None:
        return counter(current, key), None
    baseline, _ = counters_at(snapshot, start - timedelta(days=1))
    since = None
    if baseline is None:
        baseline, since_day = earliest_known(snapshot)
        since = since_day if since_day > start else None
    return max(0.0, counter(current, key) - counter(baseline, key)), since


# --- état d'un personnage pour sa fiche ----------------------------------------------------------------


def _iso(ts: Any) -> str | None:
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    return None


def character_progress(character: Character, now: datetime | None = None) -> dict | None:
    snapshot = latest_snapshot(character)
    if snapshot is None:
        return None
    now = now or timezone.now()
    data = snapshot.data if isinstance(snapshot.data, dict) else {}
    counters = data.get("counters") if isinstance(data.get("counters"), dict) else {}
    today = now.astimezone(PARIS).date()
    week_start = today - timedelta(days=6)

    def tile(key: str) -> dict:
        value, _ = delta(snapshot, key, week_start, today)
        return {"total": counter(counters, key), "week": value}

    bosses = counters.get("bosses") if isinstance(counters.get("bosses"), dict) else {}
    boss_list = sorted(
        (
            {
                "id": int(k) if str(k).isdigit() else None,
                "name": v.get("name") or str(k),
                "kills": int(number(v.get("n"))),
                "first": _iso(v.get("first")),
                "last": _iso(v.get("last")),
            }
            for k, v in bosses.items()
            if isinstance(v, dict)
        ),
        key=lambda b: (-b["kills"], b["name"]),
    )

    gear_raw = data.get("gear") if isinstance(data.get("gear"), dict) else {}
    item_ids = [p["id"] for p in gear_raw.values() if isinstance(p, dict) and isinstance(p.get("id"), int)]
    items = {i.id: i for i in Item.objects.filter(id__in=item_ids)}
    gear = []
    for slot, piece in gear_raw.items():
        if not isinstance(piece, dict) or not isinstance(piece.get("id"), int):
            continue
        item = items.get(piece["id"])
        gear.append(
            {
                "slot": slot,
                "item_id": piece["id"],
                "enchant_id": piece.get("ench") if isinstance(piece.get("ench"), int) else None,
                "name": item.name if item else None,
                "quality": item.quality if item else None,
                "icon": item.icon if item else None,
                "item_level": item.item_level if item else None,
            }
        )

    reputations_raw = data.get("reputations") if isinstance(data.get("reputations"), dict) else {}
    reputations = sorted(
        (
            {
                "id": int(k) if str(k).isdigit() else None,
                "name": v.get("n") or str(k),
                "value": int(number(v.get("v"))),
                "reaction": int(number(v.get("r"))) or None,
            }
            for k, v in reputations_raw.items()
            if isinstance(v, dict)
        ),
        key=lambda r: (-(r["reaction"] or 0), -r["value"]),
    )

    lockouts = [
        {
            "name": lk.get("name"),
            "reset_at": _iso(lk.get("reset_at")),
            "raid": bool(lk.get("raid")),
            "killed": int(number(lk.get("killed"))),
            "bosses": int(number(lk.get("bosses"))),
        }
        for lk in (data.get("lockouts") or [])
        if isinstance(lk, dict)
    ]

    pvp = data.get("pvp") if isinstance(data.get("pvp"), dict) else {}
    bg = pvp.get("bg") if isinstance(pvp.get("bg"), dict) else {}
    battlegrounds = sorted(
        (
            {"map": k, "played": int(number(v.get("played"))), "won": int(number(v.get("won")))}
            for k, v in bg.items()
            if isinstance(v, dict)
        ),
        key=lambda b: -b["played"],
    )

    events = [e for e in (data.get("events") or []) if isinstance(e, dict)]
    levels = [
        {"at": _iso(e.get("t")), "level": int(number(e.get("level")))}
        for e in events
        if e.get("k") == "level" and _iso(e.get("t"))
    ]

    journal = data.get("journal") if isinstance(data.get("journal"), dict) else {}
    series = [
        {
            "day": day,
            "deaths": counter(c, "deaths"),
            "boss_kills": counter(c, "boss_kills"),
            "bg_played": counter(c, "bg_played"),
            "mining": counter(c, "gathering.mining"),
            "herbalism": counter(c, "gathering.herbalism"),
            "skinning": counter(c, "gathering.skinning"),
            "fishing": counter(c, "gathering.fishing"),
            "quests": counter(c, "quests"),
        }
        for day, c in sorted(journal.items())
        if isinstance(c, dict)
    ]

    syncs = [
        {
            "received_at": b.received_at.isoformat(),
            "source": b.source,
            "device": b.device.name if b.device else None,
        }
        for b in ImportBatch.objects.filter(snapshots__character=character)
        .select_related("device")
        .distinct()
        .order_by("-received_at")[:5]
    ]

    gathering = counters.get("gathering") if isinstance(counters.get("gathering"), dict) else {}
    return {
        "synced_at": snapshot.exported_at.isoformat(),
        "counting_since": _iso(data.get("counting_since")),
        "played": data.get("played") if isinstance(data.get("played"), (int, float)) else None,
        "tiles": {
            "boss_kills": tile("boss_kills"),
            "dungeons_done": tile("dungeons_done"),
            "raids_done": tile("raids_done"),
            "deaths": tile("deaths"),
            "bg_played": tile("bg_played"),
            "bg_won": tile("bg_won"),
            "quests": tile("quests"),
            "crafted_total": tile("crafted_total"),
        },
        "gathering": {
            k: int(number(gathering.get(k))) for k in ("mining", "herbalism", "skinning", "fishing")
        },
        "gathering_week": {
            k: delta(snapshot, f"gathering.{k}", week_start, today)[0]
            for k in ("mining", "herbalism", "skinning", "fishing")
        },
        "pvp": {
            "hk_lifetime": pvp.get("hk_lifetime")
            if isinstance(pvp.get("hk_lifetime"), (int, float))
            else None,
            "rank": pvp.get("rank") if isinstance(pvp.get("rank"), (int, float)) else None,
            "battlegrounds": battlegrounds,
        },
        "attunements": {k: bool(v) for k, v in (data.get("attunements") or {}).items()}
        if isinstance(data.get("attunements"), dict)
        else {},
        "lockouts": lockouts,
        "reputations": reputations,
        "bosses": boss_list,
        "gear": gear,
        "spec_tab": data.get("spec_tab") if isinstance(data.get("spec_tab"), int) else None,
        "levels": levels,
        "series": series,
        "syncs": syncs,
    }
