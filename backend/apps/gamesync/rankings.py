"""
Classements de guilde : différence des compteurs cumulés entre le début de la période et maintenant, par
joueur (somme de ses personnages) ou par personnage. Plus les données du site (crafts livrés, présence aux
événements), la progression de guilde (premiers kills) et quelques totaux.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from apps.characters.models import Character
from apps.crafting.models import CraftRequest, CraftStatus
from apps.events.models import EventStatus, Placement, Signup, SignupStatus
from apps.gamedata.models import Instance

from .encounters import ENCOUNTERS, GUILD_KILL_MIN_MEMBERS, INSTANCE_ORDER, INSTANCE_SIZE
from .models import CharacterSnapshot, WeeklyTitle
from .progress import delta, latest_snapshots, number
from .services import PARIS

SEASON_START = date(2026, 11, 4)
PERIODS = ("week", "month", "season", "all")
MIN_BG_FOR_RATE = 1


@dataclass
class Category:
    key: str
    label: str
    group: str
    unit: str = ""
    counter: str | None = None  # clé dans les compteurs de l'addon
    source: str = "addon"  # ou "site"
    shame: bool = False
    note: str = ""


CATEGORIES: list[Category] = [
    Category("boss_kills", "Boss tués", "pve", counter="boss_kills"),
    Category("dungeons_done", "Donjons terminés", "pve", counter="dungeons_done"),
    Category("raids_done", "Raids terminés", "pve", counter="raids_done"),
    Category("deaths", "Les fragiles", "pve", counter="deaths", shame=True),
    Category("hk", "Victoires honorables", "pvp", counter="hk"),
    Category("bg_won", "Champs de bataille gagnés", "pvp", counter="bg_won"),
    Category("bg_played", "Champs de bataille joués", "pvp", counter="bg_played"),
    Category(
        "bg_rate",
        "Taux de victoire en BG",
        "pvp",
        unit="%",
        counter="bg_rate",
        note="Dès le premier champ de bataille joué sur la période.",
    ),
    Category("mining", "Minerais récoltés", "gathering", counter="gathering.mining"),
    Category("herbalism", "Herbes récoltées", "gathering", counter="gathering.herbalism"),
    Category("skinning", "Peaux récoltées", "gathering", counter="gathering.skinning"),
    Category("fishing", "Poissons pêchés", "gathering", counter="gathering.fishing"),
    Category("crafted_total", "Objets fabriqués", "crafting", counter="crafted_total"),
    Category("crafts_delivered", "Demandes de craft livrées", "crafting", source="site"),
    Category("attendance", "Présence aux événements", "guild", source="site"),
    Category("quests", "Quêtes rendues", "guild", counter="quests"),
    Category("playtime", "Temps de jeu", "optin", unit="h", counter="played"),
]
CATEGORY_BY_KEY = {c.key: c for c in CATEGORIES}

WEEKLY_TITLES: list[tuple[str, str, str]] = [
    ("mining", "Mineur de la semaine", "mining"),
    ("bg", "Calamité de la Horde", "hk"),
    ("boss", "Fléau des boss", "boss_kills"),
    ("shame", "Mort le plus souvent", "deaths"),
]


def period_bounds(period: str, now: datetime) -> tuple[date | None, date]:
    """(premier jour inclus ou None pour « total », dernier jour inclus) en Europe/Paris."""
    today = now.astimezone(PARIS).date()
    if period == "week":
        return today - timedelta(days=today.weekday()), today
    if period == "month":
        return today.replace(day=1), today
    if period == "season":
        return SEASON_START, today
    return None, today


def previous_bounds(period: str, start: date | None) -> tuple[date, date] | None:
    if start is None:
        return None
    if period == "week":
        return start - timedelta(days=7), start - timedelta(days=1)
    if period == "month":
        last_month_end = start - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    return None


@dataclass
class Entry:
    user_id: int
    display_name: str
    character_id: int | None
    character_name: str
    character_class: str
    value: float
    since: date | None = None
    rank: int = 0
    previous_rank: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _snapshot_values(
    snapshots: dict[int, CharacterSnapshot], key: str, start: date | None, end: date
) -> dict[int, tuple[float, date | None]]:
    """Valeur de progression par personnage."""
    out = {}
    for character_id, snapshot in snapshots.items():
        if key == "bg_rate":
            won, since = delta(snapshot, "bg_won", start, end)
            played, _ = delta(snapshot, "bg_played", start, end)
            out[character_id] = ((round(100 * won / played) if played >= MIN_BG_FOR_RATE else 0.0), since)
        elif key == "played":
            data = snapshot.data if isinstance(snapshot.data, dict) else {}
            out[character_id] = (round(number(data.get("played")) / 3600, 1), None)
        else:
            out[character_id] = delta(snapshot, key, start, end)
    return out


def _site_values(key: str, start: date | None, end: date) -> dict[int, float]:
    """Valeurs par utilisateur venant du site lui-même."""
    tz_start = datetime.combine(start, datetime.min.time(), tzinfo=PARIS) if start else None
    tz_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=PARIS)
    if key == "crafts_delivered":
        qs = CraftRequest.objects.filter(
            status=CraftStatus.DELIVERED, delivered_at__lt=tz_end, crafter__isnull=False
        )
        if tz_start:
            qs = qs.filter(delivered_at__gte=tz_start)
        return {
            row["crafter__owner"]: float(row["n"])
            for row in qs.values("crafter__owner").annotate(n=Count("id"))
        }
    if key == "attendance":
        qs = Signup.objects.filter(
            status=SignupStatus.PRESENT,
            placement=Placement.CONFIRMED,
            event__status=EventStatus.PLANNED,
            event__starts_at__lt=tz_end - timedelta(hours=1),
        )
        if tz_start:
            qs = qs.filter(event__starts_at__gte=tz_start)
        return {row["user"]: float(row["n"]) for row in qs.values("user").annotate(n=Count("id"))}
    return {}


def _rank(entries: list[Entry]) -> list[Entry]:
    entries.sort(key=lambda e: (-e.value, e.display_name.lower(), e.character_name.lower()))
    rank = 0
    last_value = None
    for i, entry in enumerate(entries, start=1):
        if entry.value != last_value:
            rank = i
            last_value = entry.value
        entry.rank = rank
    return entries


def category_entries(
    category: Category, snapshots: dict[int, CharacterSnapshot], by: str, start: date | None, end: date
) -> list[Entry]:
    entries: list[Entry] = []
    if category.source == "site":
        values = _site_values(category.key, start, end)
        users = {
            c.owner_id: c
            for c in Character.objects.filter(owner_id__in=values, is_main=True).select_related(
                "owner", "player_class"
            )
        }
        for user_id, value in values.items():
            if value <= 0:
                continue
            main = users.get(user_id)
            display = main.owner.display_name if main else str(user_id)
            entries.append(
                Entry(
                    user_id,
                    display,
                    main.pk if main else None,
                    main.name if main else "",
                    main.player_class.slug if main else "",
                    value,
                )
            )
        return _rank(entries)

    values = _snapshot_values(snapshots, category.counter or category.key, start, end)
    if by == "character":
        for character_id, (value, since) in values.items():
            if value <= 0:
                continue
            c = snapshots[character_id].character
            entries.append(
                Entry(c.owner_id, c.owner.display_name, c.pk, c.name, c.player_class.slug, value, since)
            )
        return _rank(entries)

    per_user: dict[int, Entry] = {}
    for character_id, (value, since) in values.items():
        c = snapshots[character_id].character
        entry = per_user.get(c.owner_id)
        if entry is None:
            entry = Entry(c.owner_id, c.owner.display_name, c.pk, c.name, c.player_class.slug, 0.0, since)
            per_user[c.owner_id] = entry
        if category.key == "bg_rate":
            entry.value = max(entry.value, value)  # un taux ne s'additionne pas : on garde le meilleur perso
        else:
            entry.value += value
        if since and (entry.since is None or since < entry.since):
            entry.since = since
        if value > entry.extra.get("best_value", -1):
            entry.extra["best_value"] = value
            entry.character_id, entry.character_name, entry.character_class = (
                c.pk,
                c.name,
                c.player_class.slug,
            )
    return _rank([e for e in per_user.values() if e.value > 0])


def compute_rankings(
    period: str = "week", by: str = "player", now: datetime | None = None, limit: int = 10
) -> dict:
    now = now or timezone.now()
    period = period if period in PERIODS else "week"
    by = by if by in ("player", "character") else "player"
    start, end = period_bounds(period, now)
    previous = previous_bounds(period, start)
    snapshots = latest_snapshots()

    categories = []
    for category in CATEGORIES:
        entries = category_entries(category, snapshots, by, start, end)
        if previous:
            before = {
                (e.user_id, e.character_id if by == "character" else None): e.rank
                for e in category_entries(category, snapshots, by, previous[0], previous[1])
            }
            for entry in entries:
                entry.previous_rank = before.get(
                    (entry.user_id, entry.character_id if by == "character" else None)
                )
        categories.append(
            {
                "key": category.key,
                "label": category.label,
                "group": category.group,
                "unit": category.unit,
                "shame": category.shame,
                "note": category.note,
                "total": len(entries),
                "entries": [
                    {
                        "rank": e.rank,
                        "user": {"id": e.user_id, "display_name": e.display_name},
                        "character": {
                            "id": e.character_id,
                            "name": e.character_name,
                            "player_class": e.character_class,
                        }
                        if e.character_id
                        else None,
                        "value": e.value,
                        "previous_rank": e.previous_rank,
                        "since": e.since.isoformat() if e.since else None,
                    }
                    for e in entries[:limit]
                ],
                "all_entries": [{"rank": e.rank, "user_id": e.user_id, "value": e.value} for e in entries],
            }
        )

    week_start, week_end = period_bounds("week", now)
    totals = {
        key: sum(v for v, _ in _snapshot_values(snapshots, key, week_start, week_end).values())
        for key in ("boss_kills", "dungeons_done", "bg_played", "gathering.mining", "crafted_total", "deaths")
    }
    return {
        "period": period,
        "by": by,
        "start": start.isoformat() if start else None,
        "end": end.isoformat(),
        "players": len({s.character.owner_id for s in snapshots.values()}),
        "characters": len(snapshots),
        "categories": categories,
        "titles": current_titles(now),
        "progression": guild_progression(snapshots),
        "levels": level_distribution(),
        "week_totals": totals,
    }


# --- titres de la semaine ---------------------------------------------------------------------------------


def current_titles(now: datetime) -> list[dict]:
    """Titres de la dernière semaine close (attribués le lundi à 10h, figés ensuite)."""
    today = now.astimezone(PARIS).date()
    this_monday = today - timedelta(days=today.weekday())
    titles = WeeklyTitle.objects.filter(week_start=this_monday - timedelta(days=7)).select_related(
        "user", "character"
    )
    return [
        {
            "key": t.key,
            "label": t.label,
            "week_start": t.week_start.isoformat(),
            "value": t.value,
            "user": {"id": t.user_id, "display_name": t.user.display_name},
            "character": {
                "id": t.character_id,
                "name": t.character.name,
                "player_class": t.character.player_class.slug,
            }
            if t.character
            else None,
        }
        for t in titles
    ]


# --- progression de guilde ---------------------------------------------------------------------------


def guild_progression(snapshots: dict[int, CharacterSnapshot] | None = None) -> list[dict]:
    snapshots = snapshots if snapshots is not None else latest_snapshots()
    kills: dict[tuple[int, int], dict] = {}  # (encounter, créneau de 5 min) → infos
    names: dict[int, str] = {}
    for snapshot in snapshots.values():
        data = snapshot.data if isinstance(snapshot.data, dict) else {}
        for event in data.get("events") or []:
            if (
                not isinstance(event, dict)
                or event.get("k") != "boss"
                or not isinstance(event.get("id"), int)
            ):
                continue
            t = number(event.get("t"))
            if t <= 0:
                continue
            encounter = event["id"]
            names.setdefault(encounter, str(event.get("name") or encounter))
            key = (encounter, int(t // 300))
            group = kills.setdefault(key, {"t": t, "guild": 0, "members": set()})
            group["guild"] = max(group["guild"], int(number(event.get("guild"))))
            group["members"].add(snapshot.character.owner_id)

    per_boss: dict[int, dict] = {}
    for (encounter, _), group in kills.items():
        boss = per_boss.setdefault(encounter, {"kills": 0, "first": None, "last": None, "best_group": 0})
        guild_count = max(group["guild"], len(group["members"]))
        boss["best_group"] = max(boss["best_group"], guild_count)
        if guild_count >= GUILD_KILL_MIN_MEMBERS:
            boss["kills"] += 1
            boss["first"] = group["t"] if boss["first"] is None else min(boss["first"], group["t"])
            boss["last"] = group["t"] if boss["last"] is None else max(boss["last"], group["t"])

    instance_names = {i.slug: i.name for i in Instance.objects.all()}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for encounter, info in per_boss.items():
        slug, order = ENCOUNTERS.get(encounter, ("autres", 999))
        grouped[slug].append(
            {
                "id": encounter,
                "name": names.get(encounter, str(encounter)),
                "order": order,
                "kills": info["kills"],
                "first_kill": datetime.fromtimestamp(info["first"], tz=UTC).isoformat()
                if info["first"]
                else None,
                "last_kill": datetime.fromtimestamp(info["last"], tz=UTC).isoformat()
                if info["last"]
                else None,
                "best_group": info["best_group"],
            }
        )
    # Les boss connus mais jamais tués apparaissent quand même, pour la barre d'avancement.
    for encounter, (slug, order) in ENCOUNTERS.items():
        if encounter not in per_boss and any(
            b["id"] in ENCOUNTERS and ENCOUNTERS[b["id"]][0] == slug for b in grouped.get(slug, [])
        ):
            grouped[slug].append(
                {
                    "id": encounter,
                    "name": names.get(encounter, f"Boss {order + 1}"),
                    "order": order,
                    "kills": 0,
                    "first_kill": None,
                    "last_kill": None,
                    "best_group": 0,
                }
            )
    result = []
    for slug in INSTANCE_ORDER:
        bosses = grouped.get(slug)
        if not bosses:
            continue
        bosses.sort(key=lambda b: (b["order"], b["name"]))
        killed = sum(1 for b in bosses if b["kills"] > 0)
        result.append(
            {
                "slug": slug,
                "name": instance_names.get(
                    slug, "Autres rencontres" if slug == "autres" else slug.replace("-", " ").title()
                ),
                "killed": killed,
                "total": INSTANCE_SIZE.get(slug, len(bosses)),
                "bosses": bosses,
                "first_clear": max((b["first_kill"] for b in bosses if b["first_kill"]), default=None)
                if killed == INSTANCE_SIZE.get(slug)
                else None,
            }
        )
    return result


def level_distribution() -> list[dict]:
    bins = [
        (1, 19, "1–19"),
        (20, 29, "20–29"),
        (30, 39, "30–39"),
        (40, 49, "40–49"),
        (50, 59, "50–59"),
        (60, 60, "60"),
    ]
    counts = Character.objects.filter(owner__is_active=True).aggregate(
        **{f"b{i}": Count("id", filter=Q(level__gte=lo, level__lte=hi)) for i, (lo, hi, _) in enumerate(bins)}
    )
    return [{"label": label, "count": counts[f"b{i}"]} for i, (_, _, label) in enumerate(bins)]
