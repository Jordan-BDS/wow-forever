"""
Têtes mises à prix (Wanted), lot 3 : agrégation des événements exportés par l'addon, sans table recalculée,
comme les classements. Un événement `death` dont le tueur est un joueur (`player`) donne un point à ce joueur,
jamais remis à zéro (décision du 9 novembre 2026) ; un événement `pk` (kill de joueur, lu dans le message de
victoire honorable) marque un kill, compté une fois par ennemi et par minute : tout le groupe est crédité et
chaque chasseur exporte le sien. L'ennemi d'un `pk` est reconnu par son nom exact, ou par le prénom seul s'il
est unique. Le GM retire un nom (PNJ homonyme, erreur) avec `WantedExclusion`, depuis l'administration.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.utils import timezone

from .models import WantedExclusion
from .progress import latest_snapshots, number
from .services import PARIS

WANTED_LIMIT = 40
COMPANION_LIMIT = 200  # Data.WANTED_MAX de l'addon
KILL_DEDUPE_SECONDS = 60  # Data.WANTED_KILL_DEDUPE de l'addon


def key_of(name: Any) -> str:
    """Clé d'un ennemi : son nom en minuscules, espaces normalisés (même règle que l'addon)."""
    return " ".join(str(name or "").split()).lower()


def _bounds(start: date | None, end: date) -> tuple[float, float]:
    lo = datetime.combine(start, datetime.min.time(), tzinfo=PARIS).timestamp() if start else 0.0
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=PARIS).timestamp()
    return lo, hi


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=UTC).isoformat()


def _who(character) -> dict:
    return {
        "user": {"id": character.owner_id, "display_name": character.owner.display_name},
        "character": {
            "id": character.pk,
            "name": character.name,
            "player_class": character.player_class.slug,
        },
    }


def _position(event: dict) -> dict | None:
    if not (isinstance(event.get("map"), int) and _is_num(event.get("x")) and _is_num(event.get("y"))):
        return None
    return {"map": event["map"], "x": float(event["x"]), "y": float(event["y"])}


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _new_enemy(key: str, name: str) -> dict:
    return {
        "key": key,
        "name": name,
        "class": "",
        "points": 0,
        "kills": 0,
        "victims": {},
        "hunters": {},
        "kill_times": [],
        "last_death": None,
        "last_kill": None,
        "last_seen": None,
    }


def _match(enemies: dict[str, dict], name: str) -> dict | None:
    """Clé exacte, sinon le seul ennemi qui porte ce prénom (le message de victoire honorable peut ne donner
    que le prénom là où le récapitulatif de mort donnait prénom et nom, ou l'inverse)."""
    key = key_of(name)
    if key in enemies:
        return enemies[key]
    first = key.split(" ")[0] if key else ""
    if not first:
        return None
    candidates = [enemy for k, enemy in enemies.items() if k.split(" ")[0] == first]
    return candidates[0] if len(candidates) == 1 else None


def _serialize(enemy: dict) -> dict:
    last_death, last_kill, last_seen = enemy["last_death"], enemy["last_kill"], enemy["last_seen"]
    return {
        "key": enemy["key"],
        "name": enemy["name"],
        "class": enemy["class"],
        "points": enemy["points"],
        "kills": enemy["kills"],
        "victims": len(enemy["victims"]),
        "victim_names": [v["character"]["name"] for v in enemy["victims"].values()][:6],
        "hunters": len(enemy["hunters"]),
        "last_death": {
            "at": _iso(last_death["t"]),
            "zone": last_death["zone"],
            "victim": last_death["victim"],
        }
        if last_death
        else None,
        "last_kill": {"at": _iso(last_kill["t"]), "zone": last_kill["zone"], "by": last_kill["by"]}
        if last_kill
        else None,
        "last_seen": {"at": _iso(last_seen["t"]), **last_seen["position"]} if last_seen else None,
    }


def guild_wanted(
    snapshots: dict | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = WANTED_LIMIT,
) -> list[dict]:
    """Ennemis par prime décroissante sur la période (`start` None : depuis l'installation de l'addon)."""
    snapshots = snapshots if snapshots is not None else latest_snapshots()
    end = end or timezone.now().astimezone(PARIS).date()
    lo, hi = _bounds(start, end)
    excluded = set(WantedExclusion.objects.values_list("name", flat=True))
    enemies: dict[str, dict] = {}
    kills: list[tuple[dict, float, Any]] = []
    for snapshot in snapshots.values():
        data = snapshot.data if isinstance(snapshot.data, dict) else {}
        character = snapshot.character
        for event in data.get("events") or []:
            if not isinstance(event, dict):
                continue
            t = number(event.get("t"))
            if not lo <= t < hi:
                continue
            kind = event.get("k")
            if kind == "death" and event.get("player") is True:
                killer = event.get("killer")
                if not isinstance(killer, str) or not killer.strip():
                    continue
                key = key_of(killer)
                if key in excluded:
                    continue
                enemy = enemies.setdefault(key, _new_enemy(key, " ".join(killer.split())))
                enemy["points"] += 1
                kclass = event.get("kclass")
                if not enemy["class"] and isinstance(kclass, str) and kclass:
                    enemy["class"] = kclass.lower()
                who = _who(character)
                enemy["victims"][character.pk] = who
                if enemy["last_death"] is None or t > enemy["last_death"]["t"]:
                    enemy["last_death"] = {"t": t, "zone": str(event.get("zone") or ""), "victim": who}
                position = _position(event)
                if position and (enemy["last_seen"] is None or t > enemy["last_seen"]["t"]):
                    enemy["last_seen"] = {"t": t, "position": position}
            elif kind == "pk" and isinstance(event.get("name"), str) and event["name"].strip():
                kills.append((event, t, character))
    # Les kills après les morts : il faut connaître les noms complets pour reconnaître un prénom seul.
    for event, t, character in kills:
        enemy = _match(enemies, event["name"])
        if enemy is None or enemy["key"] in excluded:
            continue
        who = _who(character)
        enemy["hunters"][character.owner_id] = who
        if any(abs(seen - t) < KILL_DEDUPE_SECONDS for seen in enemy["kill_times"]):
            continue  # le même kill vu par un autre chasseur du groupe
        enemy["kill_times"].append(t)
        enemy["kills"] += 1
        if enemy["last_kill"] is None or t > enemy["last_kill"]["t"]:
            enemy["last_kill"] = {"t": t, "zone": str(event.get("zone") or ""), "by": who}
        position = _position(event)
        if position and (enemy["last_seen"] is None or t > enemy["last_seen"]["t"]):
            enemy["last_seen"] = {"t": t, "position": position}
    ordered = sorted(enemies.values(), key=lambda e: (-e["points"], -e["kills"], e["name"].lower()))
    return [_serialize(e) for e in ordered[:limit]]


def companion_wanted(snapshots: dict | None = None) -> list[dict]:
    """Le tableau de la guilde depuis le début, dans les termes de l'addon (jeton de classe en majuscules,
    dernière position en secondes), que le compagnon recopie dans `db.wanted` jeu fermé."""
    out = []
    for enemy in guild_wanted(snapshots, None, None, limit=COMPANION_LIMIT):
        last = enemy["last_seen"]
        last_at = max(
            (
                int(datetime.fromisoformat(x["at"]).timestamp())
                for x in (enemy["last_death"], enemy["last_kill"], last)
                if x
            ),
            default=None,
        )
        out.append(
            {
                "name": enemy["name"],
                "class": enemy["class"].upper(),
                "points": enemy["points"],
                "kills": enemy["kills"],
                "last_t": last_at,
                "map": last["map"] if last else None,
                "x": last["x"] if last else None,
                "y": last["y"] if last else None,
            }
        )
    return out
