"""
Têtes mises à prix (Wanted), lot 3 : agrégation des événements exportés par l'addon, sans table recalculée,
comme les classements. Un événement `death` dont le tueur est un joueur (`player`) donne un point à ce joueur,
jamais remis à zéro (décision du 9 novembre 2026) ; un événement `pk` (kill de joueur, lu dans le message de
victoire honorable) marque un kill, compté une fois par ennemi et par minute : tout le groupe est crédité et
chaque chasseur exporte le sien. L'ennemi d'un `pk` est reconnu par son nom exact, ou par le prénom seul s'il
est unique. Le GM retire un nom (PNJ homonyme, erreur) avec `WantedExclusion`, depuis l'administration.
La page /wanted du site lit le rapport détaillé : chaque mort et chaque kill, chasseurs et victimes.
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
DETAIL_LIMIT = 30  # morts et kills gardés par ennemi dans le rapport détaillé


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
            "surname": character.surname,
            "player_class": character.player_class.slug,
        },
    }


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _position(event: dict) -> dict | None:
    if not (isinstance(event.get("map"), int) and _is_num(event.get("x")) and _is_num(event.get("y"))):
        return None
    return {"map": event["map"], "x": float(event["x"]), "y": float(event["y"])}


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
        "deaths": [],  # { t, zone, victim, position }
        "kill_list": [],  # { t, zone, by, hunters, prime }
        "last_death": None,
        "last_kill": None,
        "last_seen": None,
        "first": None,
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


def _collect(snapshots: dict, start: date | None, end: date) -> tuple[dict[str, dict], list[dict]]:
    """Ennemis (clé → état complet) et participations aux kills (une par événement `pk` reconnu, doublons du
    groupe compris : elles servent aux chasseurs, pas au compteur de l'ennemi). Un `pk` marqué `bg` (champ de
    bataille, arène) compte dans le compteur du personnage mais pas ici."""
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
                zone = str(event.get("zone") or "")
                position = _position(event)
                enemy["deaths"].append({"t": t, "zone": zone, "victim": who, "position": position})
                if enemy["last_death"] is None or t > enemy["last_death"]["t"]:
                    enemy["last_death"] = {"t": t, "zone": zone, "victim": who}
                if position and (enemy["last_seen"] is None or t > enemy["last_seen"]["t"]):
                    enemy["last_seen"] = {"t": t, "position": position}
                enemy["first"] = t if enemy["first"] is None else min(enemy["first"], t)
            elif kind == "pk" and isinstance(event.get("name"), str) and event["name"].strip():
                if event.get("bg") is True:
                    continue
                kills.append((event, t, character))
    # Les kills après les morts : il faut connaître les noms complets pour reconnaître un prénom seul.
    participations: list[dict] = []
    for event, t, character in sorted(kills, key=lambda k: k[1]):
        enemy = _match(enemies, event["name"])
        if enemy is None:
            continue
        who = _who(character)
        enemy["hunters"][character.owner_id] = who
        prime = int(number(event.get("prime")))
        participations.append({"enemy": enemy["key"], "t": t, "who": who, "prime": prime})
        same = next((k for k in enemy["kill_list"] if abs(k["t"] - t) < KILL_DEDUPE_SECONDS), None)
        if same is not None:
            same["hunters"].append(who)  # le même kill vu par un autre chasseur du groupe
            continue
        zone = str(event.get("zone") or "")
        enemy["kill_times"].append(t)
        enemy["kills"] += 1
        enemy["kill_list"].append({"t": t, "zone": zone, "by": who, "hunters": [who], "prime": prime})
        if enemy["last_kill"] is None or t > enemy["last_kill"]["t"]:
            enemy["last_kill"] = {"t": t, "zone": zone, "by": who}
        position = _position(event)
        if position and (enemy["last_seen"] is None or t > enemy["last_seen"]["t"]):
            enemy["last_seen"] = {"t": t, "position": position}
    return enemies, participations


def _ordered(enemies: dict[str, dict]) -> list[dict]:
    return sorted(enemies.values(), key=lambda e: (-e["points"], -e["kills"], e["name"].lower()))


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


def _serialize_detail(enemy: dict) -> dict:
    out = _serialize(enemy)
    deaths = sorted(enemy["deaths"], key=lambda d: -d["t"])[:DETAIL_LIMIT]
    kills = sorted(enemy["kill_list"], key=lambda k: -k["t"])[:DETAIL_LIMIT]
    zones: dict[str, int] = {}
    for d in enemy["deaths"]:
        if d["zone"]:
            zones[d["zone"]] = zones.get(d["zone"], 0) + 1
    out.update(
        {
            "first_seen": _iso(enemy["first"]) if enemy["first"] is not None else None,
            "deaths": [{"at": _iso(d["t"]), "zone": d["zone"], "victim": d["victim"]} for d in deaths],
            "kill_list": [
                {
                    "at": _iso(k["t"]),
                    "zone": k["zone"],
                    "by": k["by"],
                    "prime": k["prime"],
                    "hunters": [h["character"]["name"] for h in k["hunters"]],
                }
                for k in kills
            ],
            "zones": [
                {"zone": zone, "deaths": n}
                for zone, n in sorted(zones.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
            ],
        }
    )
    return out


def guild_wanted(
    snapshots: dict | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = WANTED_LIMIT,
) -> list[dict]:
    """Ennemis par prime décroissante sur la période (`start` None : depuis l'installation de l'addon)."""
    snapshots = snapshots if snapshots is not None else latest_snapshots()
    end = end or timezone.now().astimezone(PARIS).date()
    enemies, _ = _collect(snapshots, start, end)
    return [_serialize(e) for e in _ordered(enemies)[:limit]]


def wanted_report(snapshots: dict | None = None, start: date | None = None, end: date | None = None) -> dict:
    """La page /wanted : chaque ennemi avec ses morts et ses kills, les chasseurs (participations et primes
    encaissées, telles que l'addon les a vues) et les victimes (morts par des joueurs recherchés)."""
    snapshots = snapshots if snapshots is not None else latest_snapshots()
    end = end or timezone.now().astimezone(PARIS).date()
    enemies, participations = _collect(snapshots, start, end)
    ordered = _ordered(enemies)
    hunters: dict[int, dict] = {}
    for p in participations:
        hunter = hunters.setdefault(
            p["who"]["user"]["id"], {**p["who"], "kills": 0, "bounty": 0, "enemies": set()}
        )
        hunter["kills"] += 1
        hunter["bounty"] += p["prime"]
        hunter["enemies"].add(p["enemy"])
    victims: dict[int, dict] = {}
    for enemy in ordered:
        for d in enemy["deaths"]:
            victim = victims.setdefault(
                d["victim"]["character"]["id"], {**d["victim"], "deaths": 0, "enemies": set(), "last": 0.0}
            )
            victim["deaths"] += 1
            victim["enemies"].add(enemy["key"])
            victim["last"] = max(victim["last"], d["t"])
    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat(),
        "totals": {
            "enemies": len(ordered),
            "points": sum(e["points"] for e in ordered),
            "kills": sum(e["kills"] for e in ordered),
            "victims": len(victims),
            "hunters": len(hunters),
        },
        "enemies": [_serialize_detail(e) for e in ordered],
        "hunters": [
            {**{k: v for k, v in h.items() if k != "enemies"}, "enemies": len(h["enemies"])}
            for h in sorted(
                hunters.values(), key=lambda h: (-h["bounty"], -h["kills"], h["user"]["display_name"])
            )
        ],
        "victims": [
            {
                **{k: v for k, v in v.items() if k not in ("enemies", "last")},
                "enemies": len(v["enemies"]),
                "last": _iso(v["last"]) if v["last"] else None,
            }
            for v in sorted(victims.values(), key=lambda v: (-v["deaths"], v["character"]["name"]))
        ],
    }


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
