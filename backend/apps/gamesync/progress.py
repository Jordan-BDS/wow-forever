"""
Lecture des instantanés bruts : état courant d'un personnage, valeur des compteurs à une date, séries pour les
courbes. Tout vient du JSON écrit par l'addon (`CharacterSnapshot.data`), jamais d'une table recalculée.

Un personnage peut être joué depuis plusieurs installations de l'addon (deux PC, une réinstallation) : chacune
compte depuis zéro et ne connaît pas les autres. Le site garde le dernier instantané de chaque installation et
les fusionne (`merge_installs`) : compteurs additionnés, journal additionné jour par jour, créatures et
événements réunis, totaux tenus par le jeu (victoires honorables, temps de jeu) au maximum, état (équipement,
talents, métiers…) de l'export le plus récent. Les fonctions de lecture reçoivent cet instantané fusionné.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.characters.models import Character
from apps.gamedata.models import Item

from .models import CharacterSnapshot, ImportBatch, SnapshotStatus
from .services import PARIS

APPLIED = (SnapshotStatus.APPLIED, SnapshotStatus.CREATED)
MOBS_PER_CHARACTER = 30
# Compteurs cumulés, journal, événements et créatures s'additionnent entre installations ; tout le reste est
# un état, pris sur l'export le plus récent.
MERGED_KEYS = ("counters", "journal", "events", "mobs", "pvp", "played", "counting_since", "previous_guids")
# Totaux tenus par le jeu lui-même dans les compteurs : jamais additionnés (le temps de jeu, hors compteurs,
# est traité à part dans merge_installs).
GAME_TOTALS = {"hk", "hk_lifetime"}


@dataclass
class MergedSnapshot:
    """Dernier état d'un personnage, toutes installations de l'addon confondues."""

    character: Character
    exported_at: datetime
    data: dict
    installs: int = 1
    #: Installation → horodatage (epoch) du dernier export qu'elle a fourni : ce que contient cet état.
    bases: dict[str, int] = field(default_factory=dict)
    #: Instantanés qui ont servi, à conserver si cet état est recopié dans un addon (marque du compagnon).
    sources: list = field(default_factory=list)

    @property
    def character_id(self) -> int:
        return self.character.pk


def _latest_per_install(snapshots) -> list[CharacterSnapshot]:
    """Le plus récent instantané de chaque installation, du plus récent au plus ancien."""
    seen: set[str] = set()
    kept = []
    for snapshot in snapshots:  # déjà triés par -exported_at
        install = snapshot.batch.install_id
        if install in seen:
            continue
        seen.add(install)
        kept.append(snapshot)
    return kept


def latest_snapshot(character: Character) -> MergedSnapshot | None:
    snapshots = list(
        CharacterSnapshot.objects.filter(character=character, status__in=APPLIED)
        .select_related("batch")
        .order_by("-exported_at")
    )
    return merge_installs(character, snapshots) if snapshots else None


def latest_snapshots() -> dict[int, MergedSnapshot]:
    """Dernier instantané de chaque personnage, installations fusionnées (une requête)."""
    per_character: dict[int, list[CharacterSnapshot]] = {}
    queryset = (
        CharacterSnapshot.objects.filter(
            status__in=APPLIED, character__isnull=False, character__owner__is_active=True
        )
        .select_related("batch", "character__owner", "character__player_class")
        .order_by("-exported_at")
    )
    for snapshot in queryset:
        per_character.setdefault(snapshot.character_id, []).append(snapshot)
    return {
        character_id: merge_installs(snapshots[0].character, snapshots)
        for character_id, snapshots in per_character.items()
    }


# --- fusion des installations ------------------------------------------------------------------------------


def _add(a: Any, b: Any, key: str = "") -> Any:
    """Additionne deux valeurs de compteurs : dictionnaires clé à clé, nombres sommés (`first` : minimum ;
    `last` et totaux du jeu : maximum), texte conservé (le premier non vide)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = {k: deepcopy(v) for k, v in a.items()}
        for k, v in b.items():
            out[k] = _add(out[k], v, k) if k in out else deepcopy(v)
        return out
    if _is_number(a) and _is_number(b):
        if key == "first":
            return min(a, b)
        if key == "last" or key in GAME_TOTALS:
            return max(a, b)
        return a + b
    if isinstance(a, str) and a:
        return a
    return deepcopy(b) if b not in (None, "") else deepcopy(a)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _counters_at(data: dict, export_day: date, day: date) -> dict | None:
    """Compteurs cumulés d'une installation en fin de `day` : l'état courant à partir du jour de l'export,
    sinon la dernière entrée du journal à cette date ou avant, sinon rien (l'installation n'existait pas)."""
    if day >= export_day:
        return _dict(data.get("counters"))
    journal = _dict(data.get("journal"))
    candidates = sorted(k for k in journal if isinstance(k, str) and k <= day.isoformat())
    return _dict(journal[candidates[-1]]) if candidates else None


def _subtract(a: Any, b: Any, key: str = "") -> Any:
    """Ce que `a` a de plus que `b` : dictionnaires clé à clé, nombres soustraits (jamais négatifs), dates
    (`first`, `last`) et totaux du jeu gardés tels quels."""
    if isinstance(a, dict):
        b = _dict(b)
        return {k: _subtract(v, b.get(k), k) for k, v in a.items()}
    if _is_number(a) and _is_number(b):
        if key in ("first", "last") or key in GAME_TOTALS:
            return a
        return max(0, a - b)
    return deepcopy(a)


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())


def _seed_bases(data: dict) -> dict[str, int]:
    """Marque écrite par le compagnon quand il a recopié l'état du site dans l'addon : installation →
    horodatage du dernier export de celle-ci qui était compris."""
    bases = _dict(_dict(data.get("seed")).get("bases"))
    return {str(install): int(at) for install, at in bases.items() if _is_number(at)}


def _since(data: dict, base: dict, limit: int, base_day: date) -> dict:
    """La part d'un instantané postérieure à `base` (l'export de la même installation déjà compris
    ailleurs) : compteurs, créatures et champs de bataille en différence, événements et journal après."""
    out = {k: deepcopy(v) for k, v in data.items() if k not in MERGED_KEYS}
    base_counters = _dict(base.get("counters"))
    out["counters"] = _subtract(_dict(data.get("counters")), base_counters)
    out["mobs"] = _subtract(_dict(data.get("mobs")), _dict(base.get("mobs")))
    out["events"] = [
        e for e in (data.get("events") or []) if isinstance(e, dict) and number(e.get("t")) > limit
    ]
    out["journal"] = {
        key: _subtract(entry, base_counters)
        for key, entry in _dict(data.get("journal")).items()
        if isinstance(key, str) and key > base_day.isoformat() and isinstance(entry, dict)
    }
    pvp = deepcopy(_dict(data.get("pvp")))
    pvp["bg"] = _subtract(_dict(pvp.get("bg")), _dict(_dict(base.get("pvp")).get("bg")))
    out["pvp"] = pvp
    for key in ("played", "counting_since", "previous_guids"):
        if key in data:
            out[key] = deepcopy(data[key])
    return out


def merge_installs(character: Character, snapshots: list[CharacterSnapshot]) -> MergedSnapshot:
    """Fusionne le dernier instantané de chaque installation. `snapshots` : tous les instantanés appliqués du
    personnage, du plus récent au plus ancien (les anciens servent de base quand une installation a été
    recopiée dans une autre par le compagnon : on ne compte alors que ce qu'elle a fait depuis)."""
    latest = _latest_per_install(snapshots)
    primary = latest[0]
    absorbed: dict[str, int] = {}
    for s in latest:
        for install, at in _seed_bases(_dict(s.data)).items():
            if install != s.batch.install_id:
                absorbed[install] = max(absorbed.get(install, 0), at)
    parts: list[tuple[dict, date]] = []
    bases: dict[str, int] = {}
    for s in latest:
        install = s.batch.install_id
        bases[install] = _epoch(s.exported_at)
        data = _dict(s.data)
        limit = absorbed.get(install)
        if limit is not None:
            if _epoch(s.exported_at) <= limit:
                continue  # entièrement comprise dans une autre installation
            base = next(
                (b for b in snapshots if b.batch.install_id == install and _epoch(b.exported_at) <= limit),
                None,
            )
            if base is not None:
                data = _since(data, _dict(base.data), limit, day_of(base))
        parts.append((data, day_of(s)))
    if not parts:
        parts = [(_dict(primary.data), day_of(primary))]
    if len(latest) == 1:
        return MergedSnapshot(character, primary.exported_at, _dict(primary.data), 1, bases, latest)
    data = {k: deepcopy(v) for k, v in _dict(primary.data).items() if k not in MERGED_KEYS}

    counters: dict = {}
    mobs: dict = {}
    events: list = []
    bg: dict = {}
    guids: list = []
    since = []
    for part, _ in parts:
        counters = _add(counters, _dict(part.get("counters")))
        mobs = _add(mobs, _dict(part.get("mobs")))
        events.extend(e for e in (part.get("events") or []) if isinstance(e, dict))
        bg = _add(bg, _dict(_dict(part.get("pvp")).get("bg")))
        guids.extend(g for g in (part.get("previous_guids") or []) if g not in guids)
        if _is_number(part.get("counting_since")):
            since.append(part["counting_since"])
    data["counters"] = counters
    data["mobs"] = mobs
    data["events"] = sorted(events, key=lambda e: number(e.get("t")))
    data["previous_guids"] = guids
    if since:
        data["counting_since"] = min(since)

    # Journal : chaque jour connu d'au moins une installation vaut la somme de l'état de chacune ce jour-là.
    days = sorted({k for part, _ in parts for k in _dict(part.get("journal")) if isinstance(k, str)})
    journal: dict = {}
    for key in days:
        try:
            day = date.fromisoformat(key)
        except ValueError:
            continue
        total: dict = {}
        for part, export_day in parts:
            at = _counters_at(part, export_day, day)
            if at is not None:
                total = _add(total, at)
        journal[key] = total
    data["journal"] = journal

    pvp = deepcopy(_dict(parts[0][0].get("pvp")))
    lifetime = [_dict(p.get("pvp")).get("hk_lifetime") for p, _ in parts]
    lifetime = [value for value in lifetime if _is_number(value)]
    if lifetime:
        pvp["hk_lifetime"] = max(lifetime)
    if bg:
        pvp["bg"] = bg
    if pvp:
        data["pvp"] = pvp
    played = [p["played"] for p, _ in parts if _is_number(p.get("played"))]
    if played:
        data["played"] = max(played)
    return MergedSnapshot(character, primary.exported_at, data, len(latest), bases, latest)


# --- état pour le compagnon ---------------------------------------------------------------------------------

STATE_EVENTS = 500  # plafonds de l'addon (Data.MAX_EVENTS, Data.MAX_MOBS)
STATE_MOBS = 500


def companion_state(user) -> dict:
    """L'état fusionné de chaque personnage du joueur, tel que le compagnon le recopie dans l'addon d'un PC
    (complétion au lancement, jeu fermé). Les instantanés qui ont servi sont conservés : la marque que le
    compagnon écrit les désigne comme bases pour ne pas compter deux fois."""
    characters = []
    kept: list[int] = []
    queryset = Character.objects.filter(owner=user).exclude(guid="").order_by("name")
    for character in queryset:
        merged = latest_snapshot(character)
        if merged is None:
            continue
        data = merged.data
        mobs = {k: v for k, v in _dict(data.get("mobs")).items() if isinstance(v, dict)}
        if len(mobs) > STATE_MOBS:
            top = sorted(mobs.items(), key=lambda kv: -number(kv[1].get("n")))[:STATE_MOBS]
            mobs = dict(top)
        events = [e for e in (data.get("events") or []) if isinstance(e, dict)][-STATE_EVENTS:]
        characters.append(
            {
                "guid": character.guid,
                "name": data.get("name") or character.name,
                "surname": data.get("surname") or character.surname,
                "realm": data.get("realm") or character.realm,
                "class": data.get("class"),
                "race": data.get("race"),
                "level": data.get("level") if _is_number(data.get("level")) else character.level,
                "counting_since": data.get("counting_since")
                if _is_number(data.get("counting_since"))
                else None,
                "counters": _dict(data.get("counters")),
                "journal": _dict(data.get("journal")),
                "events": events,
                "mobs": mobs,
                "pvp": _dict(data.get("pvp")),
                "played": data.get("played") if _is_number(data.get("played")) else None,
                "previous_guids": [g for g in (data.get("previous_guids") or []) if isinstance(g, str)],
                "bases": merged.bases,
            }
        )
        kept.extend(s.pk for s in merged.sources)
    CharacterSnapshot.objects.filter(pk__in=kept, kept=False).update(kept=True)
    from .wanted import companion_wanted  # import local : wanted.py lit ce module

    # Le tableau Wanted de toute la guilde : un joueur seul en ligne a quand même les têtes mises à prix.
    return {"seed_at": _epoch(timezone.now()), "characters": characters, "wanted": companion_wanted()}


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


def day_of(snapshot: CharacterSnapshot | MergedSnapshot) -> date:
    return snapshot.exported_at.astimezone(PARIS).date()


def counters_at(snapshot: CharacterSnapshot | MergedSnapshot, day: date) -> tuple[dict | None, date | None]:
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


def earliest_known(snapshot: CharacterSnapshot | MergedSnapshot) -> tuple[dict, date]:
    """Première valeur connue (plus ancienne entrée du journal, sinon l'état courant)."""
    data = snapshot.data if isinstance(snapshot.data, dict) else {}
    journal = data.get("journal") if isinstance(data.get("journal"), dict) else {}
    keys = sorted(k for k in journal if isinstance(k, str))
    if keys:
        first = keys[0]
        return (journal[first] if isinstance(journal[first], dict) else {}), date.fromisoformat(first)
    return (data.get("counters") if isinstance(data.get("counters"), dict) else {}), day_of(snapshot)


def counting_since_day(snapshot: CharacterSnapshot) -> date | None:
    """Jour (Paris) où l'addon a commencé à compter ce personnage : ses compteurs étaient alors à zéro."""
    data = snapshot.data if isinstance(snapshot.data, dict) else {}
    value = data.get("counting_since")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not value > 0:
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC).astimezone(PARIS).date()
    except (OverflowError, OSError, ValueError):
        return None


def delta(
    snapshot: CharacterSnapshot, key: str, start: date | None, end_day: date
) -> tuple[float, date | None]:
    """Progression d'un compteur entre la veille de `start` et la fin de `end_day`.

    Sans valeur connue avant `start` : si l'addon a commencé à compter pendant la période (`counting_since`),
    la base est zéro ; sinon la plus ancienne valeur connue sert de base. Dans les deux cas le jour de départ
    réel est renvoyé quand il est postérieur à `start` (« depuis le »)."""
    current, _ = counters_at(snapshot, end_day)
    if current is None:
        return 0.0, None
    if start is None:
        return counter(current, key), None
    baseline, _ = counters_at(snapshot, start - timedelta(days=1))
    since = None
    if baseline is None:
        counting_since = counting_since_day(snapshot)
        if counting_since is not None and counting_since >= start:
            baseline, since_day = {}, counting_since
        else:
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

    mobs_raw = data.get("mobs") if isinstance(data.get("mobs"), dict) else {}
    per_mob = counters.get("mobs") if isinstance(counters.get("mobs"), dict) else {}
    mobs = sorted(
        (
            {
                "id": int(k) if str(k).isdigit() else None,
                "key": str(k),
                "name": v["name"]
                if isinstance(v.get("name"), str) and v["name"]
                else (f"Créature {k}" if str(k).isdigit() else str(k)),
                "kills": int(number(v.get("n"))),
                "week": int(delta(snapshot, f"mobs.{k}", week_start, today)[0]) if k in per_mob else 0,
                "last": _iso(v.get("last")),
            }
            for k, v in mobs_raw.items()
            if isinstance(v, dict) and number(v.get("n")) > 0
        ),
        key=lambda m: (-m["kills"], m["name"]),
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
            "kills": counter(c, "kills"),
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
            "kills": tile("kills"),
            "bg_played": tile("bg_played"),
            "bg_won": tile("bg_won"),
            "quests": tile("quests"),
            "crafted_total": tile("crafted_total"),
            "hk": tile("hk"),
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
        "mobs": mobs[:MOBS_PER_CHARACTER],
        "mobs_distinct": len(mobs),
        "gear": gear,
        "spec_tab": data.get("spec_tab") if isinstance(data.get("spec_tab"), int) else None,
        "levels": levels,
        "series": series,
        "syncs": syncs,
    }
