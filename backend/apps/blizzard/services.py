"""
Lecture de l'API Battle.net pour les personnages et la guilde du site : chaque réponse est archivée telle
quelle (`BlizzardRecord`). Les transformations vers la fiche et les classements viendront quand les formes des
réponses Forever seront connues (sonde `blizzard_probe`).
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.characters.models import Character
from apps.guild.models import GuildSettings

from .client import BlizzardClient
from .models import BlizzardRecord

#: Sous-ressources d'un personnage sondées et archivées (`profile` = la fiche elle-même).
CHARACTER_RESOURCES = (
    "profile",
    "equipment",
    "specializations",
    "professions",
    "reputations",
    "quests/completed",
    "pvp-summary",
    "encounters/dungeons",
    "encounters/raids",
    "statistics",
    "achievements",
)
GUILD_RESOURCES = ("profile", "roster", "activity", "achievements")


def slugify(text: str) -> str:
    """`Manuel Feralas` → `manuel-feralas` : minuscules, espaces en tirets, accents conservés (l'API les
    accepte encodés dans l'URL ; la sonde dira si Forever les veut autrement)."""
    text = unicodedata.normalize("NFC", text.strip().lower())
    return re.sub(r"\s+", "-", text)


def character_slug(character: Character) -> str | None:
    """`prénom-nom` : les personnages Forever s'adressent sans royaume, par prénom et nom de famille."""
    if not character.surname:
        return None
    return f"{slugify(character.name)}-{slugify(character.surname)}"


def guild_slug() -> str | None:
    name = GuildSettings.load().name
    return slugify(name) if name else None


def client_from_settings() -> BlizzardClient:
    return BlizzardClient(
        settings.BLIZZARD_CLIENT_ID,
        settings.BLIZZARD_CLIENT_SECRET,
        region=settings.BLIZZARD_REGION,
        static_version=settings.BLIZZARD_STATIC_VERSION,
    )


def _record(kind: str, slug: str, status: int, data: Any, character: Character | None) -> BlizzardRecord:
    return BlizzardRecord.objects.create(
        kind=kind,
        slug=slug,
        character=character,
        http_status=status,
        data=data if isinstance(data, (dict, list)) else {},
    )


def fetch_character(
    client: BlizzardClient, slug: str, character: Character | None = None, resources=CHARACTER_RESOURCES
) -> list[BlizzardRecord]:
    """Lit la fiche et ses sous-ressources ; une fiche absente (404) arrête là, le personnage n'est pas encore
    connu de l'API (jamais déconnecté, niveau < 10, ou slug différent)."""
    records = []
    for resource in resources:
        status, data = client.character(slug, "" if resource == "profile" else resource)
        records.append(_record(f"character/{resource}", slug, status, data, character))
        if resource == "profile" and status == 404:
            break
    return records


def fetch_guild(client: BlizzardClient, slug: str, resources=GUILD_RESOURCES) -> list[BlizzardRecord]:
    records = []
    for resource in resources:
        status, data = client.guild(slug, "" if resource == "profile" else resource)
        records.append(_record(f"guild/{resource}", slug, status, data, None))
        if resource == "profile" and status == 404:
            break
    return records


def fetch_all(client: BlizzardClient) -> dict[str, int]:
    """Tous les personnages du site qui ont un nom de famille, puis la guilde. Rejouable (une lecture par
    passage, c'est l'historique)."""
    counts = {"characters": 0, "found": 0, "missing": 0, "records": 0, "guild": 0}
    for character in Character.objects.filter(owner__is_active=True).exclude(surname="").order_by("name"):
        slug = character_slug(character)
        if not slug:
            continue
        counts["characters"] += 1
        records = fetch_character(client, slug, character)
        counts["records"] += len(records)
        if records and records[0].http_status == 200:
            counts["found"] += 1
        else:
            counts["missing"] += 1
    slug = guild_slug()
    if slug:
        records = fetch_guild(client, slug)
        counts["guild"] = len(records)
        counts["records"] += len(records)
    return counts


def describe(data: Any) -> str:
    """Un résumé d'une ligne pour la sonde : clés de premier niveau, taille des listes."""
    if isinstance(data, dict):
        parts = []
        for key, value in data.items():
            if key == "_links":
                continue
            if isinstance(value, list):
                parts.append(f"{key}[{len(value)}]")
            elif isinstance(value, dict):
                parts.append(f"{key}{{{len(value)}}}")
            else:
                parts.append(key)
        return ", ".join(parts)
    if isinstance(data, list):
        return f"liste de {len(data)}"
    return "vide"


def dump(records: list[BlizzardRecord], directory: Path) -> list[Path]:
    """Écrit chaque réponse en JSON lisible : `<dossier>/<slug>/<kind>.json`."""
    written = []
    for record in records:
        target = directory / record.slug / (record.kind.replace("/", "_") + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"http_status": record.http_status, "data": record.data}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        written.append(target)
    return written
