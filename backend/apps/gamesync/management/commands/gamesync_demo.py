# ruff: noqa: E501 — tables de démonstration volontairement compactes
"""
Données de démonstration pour la fiche vivante et les classements : des joueurs fictifs, leurs personnages et
45 jours d'activité inventée, importés par le vrai chemin (codes d'export). Réservé au développement.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import SiteRole, User
from apps.gamedata.models import Item, Recipe
from apps.gamesync import services, titles
from apps.gamesync.format import encode_export

PARIS = ZoneInfo("Europe/Paris")

PLAYERS = [
    ("Garona", "Mi-Orc", "ROGUE", "Orc"), ("Drek'Thar", "Œil-de-Loup", "SHAMAN", "Orc"),
    ("Vol'jin", "Lance-Noire", "HUNTER", "Troll"), ("Cairne", "Sabot-de-Sang", "DRUID", "Tauren"),
    ("Sylvanas", "Coursevent", "HUNTER", "Scourge"), ("Rexxar", "Sans-Peur", "WARRIOR", "Orc"),
    ("Nazgrel", "Poing-de-Fer", "WARRIOR", "Orc"), ("Gazlowe", "Boulon", "MAGE", "Troll"),
    ("Eitrigg", "Vieille-Hache", "WARRIOR", "Orc"), ("Zul'jin", "Œil-Unique", "HUNTER", "Troll"),
    ("Magatha", "Totem-Sinistre", "SHAMAN", "Tauren"), ("Varimathras", "Ombrelame", "WARLOCK", "Scourge"),
    ("Hamuul", "Totem-Rune", "DRUID", "Tauren"), ("Saurcroc", "Hurlesang", "WARRIOR", "Orc"),
    ("Rokhan", "Piste-Sombre", "ROGUE", "Troll"), ("Nathanos", "Flétrisseur", "HUNTER", "Scourge"),
    ("Thrallia", "Fille-de-Durotan", "PRIEST", "Scourge"), ("Baine", "Sabot-de-Sang", "WARRIOR", "Tauren"),
]  # fmt: skip

MC_BOSSES = [
    (663, "Lucifron"), (664, "Magmadar"), (665, "Gehennas"), (666, "Garr"), (667, "Shazzrah"), (668, "Baron Geddon"),
    (669, "Sulfuron"), (670, "Golemagg"), (671, "Majordome Executus"), (672, "Ragnaros"),
]  # fmt: skip
ONYXIA = (1084, "Onyxia")

PROFESSIONS = [171, 164, 333, 202, 182, 165, 186, 393, 197]
SKILL_SLUGS = {171: "alchemy", 164: "blacksmithing", 333: "enchanting", 202: "engineering", 182: "herbalism",
               165: "leatherworking", 186: "mining", 393: "skinning", 197: "tailoring"}  # fmt: skip
GATHERING_FOR = {186: "mining", 182: "herbalism", 393: "skinning"}
REPUTATIONS = [(609, "Cercle cénarien"), (59, "Confrérie du Thorium"), (529, "Aube d'argent"), (270, "Tribu Zandalar"),
               (76, "Orgrimmar"), (81, "Les Pitons-du-Tonnerre"), (68, "Fossoyeuse"), (530, "Trolls Sombrelance")]  # fmt: skip


class Command(BaseCommand):
    help = "Crée des joueurs et des personnages fictifs avec 45 jours d'activité (développement seulement)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Autoriser hors DEBUG.")
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Réservé au développement (DEBUG). Passer --force pour insister.")
        rng = random.Random(options["seed"])
        now = timezone.now()
        today = now.astimezone(PARIS).date()
        items = list(
            Item.objects.filter(quality__gte=3, inventory_type__gt=0).values_list("id", "inventory_type")[
                :3000
            ]
        )
        recipes_by_prof = {
            slug: list(Recipe.objects.filter(profession__slug=slug).values_list("id", flat=True)[:120])
            for slug in SKILL_SLUGS.values()
        }

        # Soirées de raid : mardis et jeudis 21h des 6 dernières semaines, progression croissante dans le Magma.
        raid_nights = []
        day = today - timedelta(days=45)
        while day <= today:
            if day.weekday() in (1, 3):
                raid_nights.append(datetime.combine(day, datetime.min.time(), tzinfo=PARIS).replace(hour=21))
            day += timedelta(days=1)
        raid_nights = [n for n in raid_nights if n < now]
        kills_by_night: dict[datetime, list[tuple[int, str]]] = {}
        for i, night in enumerate(raid_nights):
            reach = min(len(MC_BOSSES), 2 + i)  # on va un peu plus loin chaque semaine
            kills_by_night[night] = MC_BOSSES[:reach] + ([ONYXIA] if i % 2 == 1 else [])
        raiders = set(rng.sample(range(len(PLAYERS)), 12))

        created_users = 0
        for index, (name, surname, class_token, race_token) in enumerate(PLAYERS):
            discord_id = f"demo-{index + 1:03d}"
            user, created = User.objects.get_or_create(
                discord_id=discord_id,
                defaults={
                    "discord_username": name.lower(),
                    "display_name": name,
                    "site_role": SiteRole.MEMBER,
                },
            )
            created_users += int(created)
            level = 60 if index in raiders or rng.random() < 0.3 else rng.randint(12, 59)
            character = self.build_character(
                rng,
                f"Player-1-DEMO{index + 10:04d}",
                name,
                surname,
                class_token,
                race_token,
                level,
                today,
                now,
                kills_by_night if index in raiders else {},
                items,
                recipes_by_prof,
            )
            # Un alt sur un joueur sur trois.
            characters = [character]
            if index % 3 == 0:
                alt_class = rng.choice(["MAGE", "PRIEST", "WARLOCK", "ROGUE"])
                characters.append(self.build_character(
                    rng, f"Player-1-DEMOALT{index:03d}", f"{name[:6]}alt", surname, alt_class, "Scourge" if alt_class != "ROGUE" else "Orc",
                    rng.randint(8, 40), today, now, {}, items, recipes_by_prof,
                ))  # fmt: skip
            code = encode_export(
                {"v": 1, "addon": "0.1.0", "install": f"demo-{index}", "characters": characters}
            )
            try:
                batch = services.import_code(user, code, source="paste")
            except services.DuplicateImport:
                continue
            self.stdout.write(f"{name}: {batch.summary}")

        awarded = titles.award_weekly_titles(now)
        self.stdout.write(
            self.style.SUCCESS(
                f"{created_users} joueur(s) créé(s), {len(PLAYERS)} imports, {len(awarded)} titre(s) de la semaine attribué(s)."
            )
        )

    def build_character(
        self,
        rng,
        guid,
        name,
        surname,
        class_token,
        race_token,
        level,
        today,
        now,
        kills_by_night,
        items,
        recipes_by_prof,
    ):
        exported_at = now - timedelta(minutes=rng.randint(5, 600))
        counting_since = today - timedelta(days=45)
        # Compteurs cumulés jour après jour.
        counters = {"deaths": 0, "boss_kills": 0, "raids_done": 0, "dungeons_done": 0, "dungeons_entered": 0, "raids_entered": 0,
                    "bg_played": 0, "bg_won": 0, "quests": 0, "crafted_total": 0, "gathering": {}, "bosses": {}}  # fmt: skip
        gathering_kind = None
        professions = []
        for skill_line in rng.sample(PROFESSIONS, 2):
            slug = SKILL_SLUGS[skill_line]
            skill = min(300, max(10, int(level * 5 + rng.randint(-40, 20))))
            recipes = (
                rng.sample(recipes_by_prof[slug], min(len(recipes_by_prof[slug]), rng.randint(5, 40)))
                if recipes_by_prof[slug]
                else []
            )
            professions.append({"id": skill_line, "skill": skill, "max": 300, "recipes": sorted(recipes)})
            if skill_line in GATHERING_FOR:
                gathering_kind = GATHERING_FOR[skill_line]
        if gathering_kind is None and rng.random() < 0.5:
            gathering_kind = "fishing"
        activity = rng.uniform(0.3, 1.5)
        journal = {}
        events = []
        current_level = max(1, level - rng.randint(0, 25)) if level < 60 else max(40, 60 - rng.randint(0, 20))
        for offset in range(45, -1, -1):
            day = today - timedelta(days=offset)
            played_today = rng.random() < 0.7 * activity
            if played_today:
                counters["deaths"] += rng.choice([0, 0, 1, 1, 2, 3])
                counters["quests"] += rng.randint(0, 6)
                if gathering_kind:
                    counters["gathering"][gathering_kind] = counters["gathering"].get(
                        gathering_kind, 0
                    ) + rng.randint(5, 60)
                counters["crafted_total"] += rng.randint(0, 4)
                if level == 60 and rng.random() < 0.4:
                    bg = rng.randint(1, 4)
                    won = sum(1 for _ in range(bg) if rng.random() < 0.55)
                    counters["bg_played"] += bg
                    counters["bg_won"] += won
                    counters["hk"] = (
                        counters.get("hk", 0) + won * rng.randint(6, 14) + (bg - won) * rng.randint(1, 5)
                    )
                if rng.random() < 0.3:
                    counters["dungeons_entered"] += 1
                    counters["dungeons_done"] += 1
                    counters["boss_kills"] += rng.randint(2, 5)
                if current_level < level and rng.random() < 0.6:
                    current_level += 1
                    events.append(
                        {
                            "k": "level",
                            "t": int(
                                datetime.combine(day, datetime.min.time(), tzinfo=PARIS)
                                .replace(hour=20)
                                .timestamp()
                            ),
                            "level": current_level,
                        }
                    )
            for night, bosses in kills_by_night.items():
                if night.date() == day and night < now:
                    counters["raids_entered"] += 1
                    for eid, boss in bosses:
                        t = (
                            int(night.timestamp()) + MC_BOSSES.index((eid, boss)) * 900
                            if (eid, boss) in MC_BOSSES
                            else int(night.timestamp()) + 7200
                        )
                        counters["boss_kills"] += 1
                        record = counters["bosses"].setdefault(str(eid), {"n": 0, "first": t, "name": boss})
                        record["n"] += 1
                        record["last"] = t
                        events.append({"k": "boss", "id": eid, "name": boss, "t": t, "size": 40, "guild": 12})
                    if (672, "Ragnaros") in bosses or ONYXIA in bosses:
                        counters["raids_done"] += 1
                    counters["deaths"] += rng.randint(0, 2)
            if offset > 0:
                journal[day.isoformat()] = self.copy(counters)
        events.sort(key=lambda e: e["t"])
        events = events[-500:]
        gear = {}
        if items and level >= 20:
            by_type = {}
            for item_id, inv in items:
                by_type.setdefault(inv, []).append(item_id)
            for slot, inv_types in {"head": [1], "neck": [2], "shoulder": [3], "chest": [5, 20], "waist": [6], "legs": [7], "feet": [8],
                                    "wrist": [9], "hands": [10], "finger1": [11], "finger2": [11], "trinket1": [12], "trinket2": [12],
                                    "back": [16], "mainhand": [13, 17, 21], "offhand": [14, 22, 23], "ranged": [15, 26, 28]}.items():  # fmt: skip
                pool = [i for inv in inv_types for i in by_type.get(inv, [])]
                if pool and rng.random() < 0.85:
                    gear[slot] = {"id": rng.choice(pool)}
        attunements = {
            "molten-core": level == 60 and rng.random() < 0.8,
            "onyxia": level == 60 and rng.random() < 0.6,
            "blackwing-lair": level == 60 and rng.random() < 0.2,
        }
        lockouts = []
        if level == 60 and kills_by_night:
            lockouts.append(
                {
                    "name": "Cœur du Magma",
                    "reset_at": int((now + timedelta(days=rng.randint(1, 6))).timestamp()),
                    "raid": True,
                    "bosses": 10,
                    "killed": rng.randint(3, 10),
                }
            )
        reputations = {
            str(fid): {"v": rng.randint(0, 20999), "r": rng.randint(4, 7), "n": fname}
            for fid, fname in rng.sample(REPUTATIONS, 5)
        }
        pvp = {
            "hk_lifetime": counters["bg_played"] * rng.randint(8, 25),
            "rank": min(14, 1 + counters["bg_won"] // 6),
        }
        if counters["bg_played"]:
            maps = ["Goulet des Chanteguerres", "Bassin d'Arathi", "Vallée d'Alterac"]
            pvp["bg"] = {}
            remaining_played, remaining_won = counters["bg_played"], counters["bg_won"]
            for m in maps:
                played = remaining_played if m == maps[-1] else rng.randint(0, remaining_played)
                won = min(
                    played, remaining_won if m == maps[-1] else rng.randint(0, min(played, remaining_won))
                )
                pvp["bg"][m] = {"played": played, "won": won}
                remaining_played -= played
                remaining_won -= won
        spec_tab = rng.randint(1, 3)
        return {
            "guid": guid, "name": name, "surname": surname, "realm": "Forever", "class": class_token, "race": race_token,
            "level": level, "spec_tab": spec_tab, "exported_at": int(exported_at.timestamp()),
            "counting_since": int(datetime.combine(counting_since, datetime.min.time(), tzinfo=PARIS).timestamp()),
            "professions": professions, "gear": gear, "attunements": attunements, "lockouts": lockouts,
            "reputations": reputations, "pvp": pvp, "counters": counters, "journal": journal, "events": events,
        }  # fmt: skip

    @staticmethod
    def copy(value):
        if isinstance(value, dict):
            return {k: Command.copy(v) for k, v in value.items()}
        return value
