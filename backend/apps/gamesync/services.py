"""
Import des codes d'export de l'addon : appairage du compagnon, rattachement des personnages, mise à jour des
tables normalisées, archive brute. Même traitement pour un code collé sur le site ou envoyé par le compagnon.
"""

from __future__ import annotations

import hashlib
import logging
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.characters import services as character_services
from apps.characters.models import Character, CharacterProfession, CharacterSource, KnownRecipe
from apps.gamedata.models import PlayerClass, Profession, Race, Recipe
from apps.guild.models import GuildSettings

from .format import ExportError, decode_export
from .models import (
    CharacterSnapshot,
    CompanionDevice,
    IgnoredCharacter,
    ImportBatch,
    PairingCode,
    SnapshotStatus,
)

logger = logging.getLogger(__name__)

PARIS = ZoneInfo("Europe/Paris")
MIN_LEVEL_BY_DEFAULT = 10
SNAPSHOT_RETENTION_DAYS = 90
LOW_LEVEL_NOTE = "low_level"
# Bornes de `exported_at` : avant 2020 ou au-delà d'un siècle, la valeur est aberrante ; au-delà de quelques
# minutes dans le futur, c'est l'horloge du PC qui avance et la date est ramenée à maintenant (sinon tous
# les imports suivants seraient « stale » jusqu'à cette date).
EXPORTED_AT_MIN = datetime(2020, 1, 1, tzinfo=UTC)
EXPORTED_AT_MAX_AHEAD = timedelta(days=100 * 365)
CLOCK_TOLERANCE = timedelta(minutes=5)

# Jetons envoyés par l'addon (seconde valeur de UnitClass / UnitRace) → slugs de l'index du site.
RACE_TOKENS = {
    "human": "human",
    "dwarf": "dwarf",
    "nightelf": "night-elf",
    "gnome": "gnome",
    "orc": "orc",
    "scourge": "undead",
    "undead": "undead",
    "tauren": "tauren",
    "troll": "troll",
}
# Identifiant de ligne de compétence (SkillLine) → métier du site.
SKILL_LINES = {
    171: "alchemy",
    164: "blacksmithing",
    333: "enchanting",
    202: "engineering",
    182: "herbalism",
    165: "leatherworking",
    186: "mining",
    393: "skinning",
    197: "tailoring",
    185: "cooking",
    129: "first-aid",
    356: "fishing",
}


class DuplicateImport(ExportError):
    """Le même code a déjà été importé par ce joueur."""


# --- appairage -----------------------------------------------------------------------------


def create_pairing_code(user) -> PairingCode:
    """Un seul code valide à la fois par joueur ; les précédents non utilisés sont invalidés."""
    now = timezone.now()
    PairingCode.objects.filter(user=user, used_at__isnull=True).update(expires_at=now)
    for _ in range(20):
        code = "".join(secrets.choice(PairingCode.ALPHABET) for _ in range(PairingCode.LENGTH))
        if not PairingCode.objects.filter(code=code).exists():
            break
    return PairingCode.objects.create(
        user=user, code=code, expires_at=now + timedelta(minutes=PairingCode.LIFETIME_MINUTES)
    )


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@transaction.atomic
def pair_device(code: str, device_name: str) -> tuple[CompanionDevice, str]:
    """Échange un code d'appairage contre un jeton longue durée (renvoyé en clair une seule fois)."""
    now = timezone.now()
    pairing = (
        PairingCode.objects.select_for_update()
        .filter(code=code.strip().upper(), used_at__isnull=True, expires_at__gt=now, user__is_active=True)
        .select_related("user")
        .first()
    )
    if pairing is None:
        raise ExportError("Code d'appairage inconnu ou expiré : génère-en un nouveau sur le site.")
    pairing.used_at = now
    pairing.save(update_fields=["used_at"])
    raw = secrets.token_urlsafe(32)
    device = CompanionDevice.objects.create(
        user=pairing.user,
        name=(device_name or "Compagnon").strip()[:64],
        token_hash=_hash_token(raw),
        token_prefix=raw[:8],
        last_seen_at=now,
    )
    return device, raw


def device_for_token(raw: str) -> CompanionDevice | None:
    device = (
        CompanionDevice.objects.select_related("user")
        .filter(token_hash=_hash_token(raw), revoked_at__isnull=True, user__is_active=True)
        .first()
    )
    if device is not None:
        now = timezone.now()
        if device.last_seen_at is None or now - device.last_seen_at > timedelta(minutes=1):
            CompanionDevice.objects.filter(pk=device.pk).update(last_seen_at=now)
    return device


def revoke_device(device: CompanionDevice) -> None:
    if device.revoked_at is None:
        device.revoked_at = timezone.now()
        device.save(update_fields=["revoked_at"])


# --- import --------------------------------------------------------------------------------


@dataclass
class ParsedCharacter:
    guid: str
    name: str
    surname: str
    realm: str
    class_slug: str
    race_token: str
    level: int
    exported_at: datetime
    spec: str
    spec_tab: int | None
    raw: dict[str, Any]


def _to_datetime(value) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("date d'export manquante")
    if not math.isfinite(value):
        raise ValueError("date d'export invalide")
    now = timezone.now()
    try:
        exported_at = datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("date d'export invalide") from exc
    if not EXPORTED_AT_MIN <= exported_at <= now + EXPORTED_AT_MAX_AHEAD:
        raise ValueError("date d'export invalide")
    if exported_at > now + CLOCK_TOLERANCE:
        return now
    return exported_at


def parse_character(raw: Any) -> ParsedCharacter:
    if not isinstance(raw, dict):
        raise ValueError("entrée illisible")
    guid = str(raw.get("guid") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not guid or not name:
        raise ValueError("identifiant ou nom manquant")
    level = raw.get("level")
    if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= Character.MAX_LEVEL:
        raise ValueError("niveau invalide")
    return ParsedCharacter(
        guid=guid[:64],
        name=name[:24],
        surname=str(raw.get("surname") or "").strip()[:24],
        realm=str(raw.get("realm") or "").strip()[:64],
        class_slug=str(raw.get("class") or "").strip().lower(),
        race_token=str(raw.get("race") or "").strip(),
        level=level,
        exported_at=_to_datetime(raw.get("exported_at")),
        spec=str(raw.get("spec") or "").strip().lower(),
        spec_tab=raw.get("spec_tab") if isinstance(raw.get("spec_tab"), int) else None,
        raw=raw,
    )


def race_slug(token: str) -> str:
    key = token.replace("-", "").replace(" ", "").lower()
    if key in RACE_TOKENS:
        return RACE_TOKENS[key]
    if key.startswith("skyborn") or key.startswith("eolide") or key.startswith("éolide"):
        return f"skyborn-{GuildSettings.load().faction}"
    return token.lower()


def default_role(player_class: PlayerClass, spec_slug: str, spec_tab: int | None = None) -> str:
    """Rôle par défaut d'un personnage créé par l'import : celui de sa spécialisation (slug ou arbre)."""
    specs = list(player_class.specializations.order_by("order"))
    spec = None
    if spec_slug:
        spec = next((s for s in specs if s.slug == f"{player_class.slug}-{spec_slug}"), None)
    if spec is None and spec_tab and 1 <= spec_tab <= len(specs):
        spec = specs[spec_tab - 1]  # l'ordre des arbres de talents suit celui des spécialisations du site
    if spec is None and specs:
        spec = specs[0]
    roles = spec.roles if spec else []
    return roles[0] if roles else "dps"


def _client_label(client: dict | None) -> str:
    """« 12.1.5 (120105) » d'après le bloc `client` de l'export ; vide pour les anciens addons."""
    if not client:
        return ""
    version = str(client.get("version") or "").strip()
    toc = client.get("toc")
    if isinstance(toc, int) and not isinstance(toc, bool):
        return f"{version or '?'} ({toc})"[:64]
    return version[:64]


def _client_refusal(client: dict | None) -> str:
    """Note de refus si l'export vient d'un autre client que ceux acceptés (Retail, Classic…), sinon vide."""
    if not client:
        return ""  # ancien addon sans bloc client : on accepte
    accepted = GuildSettings.load().accepted_interface_set
    toc = client.get("toc")
    if not accepted or isinstance(toc, bool) or not isinstance(toc, int) or toc in accepted:
        return ""
    version = str(client.get("version") or "").strip() or "?"
    return f"Export d'un autre client ({version}, interface {toc}) : seul WoW Forever est accepté."


@transaction.atomic
def import_code(user, code: str, *, source: str, device: CompanionDevice | None = None) -> ImportBatch:
    payload = decode_export(code)
    fingerprint = hashlib.sha256("".join(code.split()).encode()).hexdigest()
    if ImportBatch.objects.filter(user=user, fingerprint=fingerprint).exists():
        raise DuplicateImport("Ce code a déjà été importé : rien de nouveau.")
    client = payload.get("client") if isinstance(payload.get("client"), dict) else None
    batch = ImportBatch.objects.create(
        user=user,
        device=device,
        source=source,
        fingerprint=fingerprint,
        format_version=int(payload.get("v") or 1),
        addon_version=str(payload.get("addon") or "")[:32],
        install_id=str(payload.get("install") or "")[:64],
        client=_client_label(client),
        code="".join(code.split()),
    )
    summary: dict[str, int] = {status: 0 for status in SnapshotStatus.values}
    summary["new_recipes"] = 0
    # Le lot est créé même refusé (empreinte mémorisée) : le compagnon ne renvoie pas le code en boucle.
    refusal = _client_refusal(client)
    for raw in payload["characters"]:
        if refusal:
            snapshot = _refuse_foreign_client(batch, raw, refusal)
        else:
            snapshot = _process_character(batch, raw, summary)
        summary[snapshot.status] += 1
    batch.summary = summary
    batch.save(update_fields=["summary"])
    character_services.ensure_owner_has_main(user)
    return batch


def _snapshot(batch: ImportBatch, parsed: ParsedCharacter | None, raw: Any, **fields) -> CharacterSnapshot:
    exported_at = parsed.exported_at if parsed else timezone.now()
    return CharacterSnapshot.objects.create(
        batch=batch,
        user=batch.user,
        guid=parsed.guid
        if parsed
        else str((raw or {}).get("guid") or "")[:64]
        if isinstance(raw, dict)
        else "",
        name=parsed.name
        if parsed
        else str((raw or {}).get("name") or "")[:24]
        if isinstance(raw, dict)
        else "",
        surname=parsed.surname if parsed else "",
        realm=parsed.realm if parsed else "",
        exported_at=exported_at,
        day=exported_at.astimezone(PARIS).date(),
        data=raw if isinstance(raw, dict) else {},
        **fields,
    )


def _refuse_foreign_client(batch: ImportBatch, raw: Any, note: str) -> CharacterSnapshot:
    """Export d'un autre client : instantané refusé, sans création ni mise en attente ni mise à jour."""
    try:
        parsed = parse_character(raw)
    except ValueError:
        parsed = None
    return _snapshot(batch, parsed, raw, status=SnapshotStatus.REFUSED, note=note)


def _process_character(batch: ImportBatch, raw: Any, summary: dict[str, int]) -> CharacterSnapshot:
    user = batch.user
    try:
        parsed = parse_character(raw)
    except ValueError as exc:
        return _snapshot(batch, None, raw, status=SnapshotStatus.REFUSED, note=f"Données invalides : {exc}")

    if IgnoredCharacter.objects.filter(user=user, guid=parsed.guid).exists():
        return _snapshot(batch, parsed, raw, status=SnapshotStatus.IGNORED, note="Ignoré à ta demande")

    existing = Character.objects.select_related("owner").filter(guid=parsed.guid).first()
    if existing is not None:
        if existing.owner_id != user.pk:
            logger.warning(
                "Import refusé : %s (%s) appartient à %s, reçu de %s",
                parsed.name,
                parsed.guid,
                existing.owner,
                user,
            )
            return _snapshot(
                batch, parsed, raw, status=SnapshotStatus.REFUSED,
                note=f"Appartient à {existing.owner.display_name} sur le site : vois un officier.",
            )  # fmt: skip
        if existing.last_synced_at and parsed.exported_at <= existing.last_synced_at:
            return _snapshot(
                batch,
                parsed,
                raw,
                character=existing,
                status=SnapshotStatus.STALE,
                note="Export plus ancien que le dernier import",
            )
        return _apply(batch, parsed, raw, existing, SnapshotStatus.APPLIED, summary)

    by_name = Character.objects.filter(owner=user, guid="", name__iexact=parsed.name)
    if parsed.surname:
        by_name = by_name.filter(surname__iexact=parsed.surname) | by_name.filter(surname="")
    match = by_name.first()
    if match is not None:
        return _apply(batch, parsed, raw, match, SnapshotStatus.APPLIED, summary, note="Rattaché par le nom")

    candidates = Character.objects.filter(
        owner=user, guid="", player_class__slug=parsed.class_slug, race__slug=race_slug(parsed.race_token)
    ).order_by("-level")
    candidate = candidates.first()
    if candidate is not None:
        return _snapshot(
            batch, parsed, raw, candidate=candidate, status=SnapshotStatus.PENDING,
            note=f"Est-ce « {candidate.name} » (même classe, même race) ? Fusionner, ou créer un personnage.",
        )  # fmt: skip

    if parsed.level < MIN_LEVEL_BY_DEFAULT:
        return _snapshot(batch, parsed, raw, status=SnapshotStatus.IGNORED, note=LOW_LEVEL_NOTE)

    return _create(batch, parsed, raw, summary)


def _create(
    batch: ImportBatch, parsed: ParsedCharacter, raw: dict, summary: dict[str, int], note: str = ""
) -> CharacterSnapshot:
    user = batch.user
    player_class = PlayerClass.objects.filter(slug=parsed.class_slug).first()
    race = Race.objects.filter(slug=race_slug(parsed.race_token)).first()
    if player_class is None or race is None:
        return _snapshot(
            batch, parsed, raw, status=SnapshotStatus.REFUSED, note="Classe ou race inconnue du site"
        )
    homonym = Character.objects.select_related("owner").filter(name__iexact=parsed.name).first()
    if homonym is not None:
        return _snapshot(
            batch, parsed, raw, status=SnapshotStatus.REFUSED,
            note=f"« {homonym.name} » existe déjà sur le site (joueur : {homonym.owner.display_name}).",
        )  # fmt: skip
    character = Character.objects.create(
        owner=user,
        name=parsed.name,
        player_class=player_class,
        race=race,
        level=parsed.level,
        main_role=default_role(player_class, parsed.spec, parsed.spec_tab),
        source=CharacterSource.ADDON,
        roles_confirmed=False,
    )
    return _apply(batch, parsed, raw, character, SnapshotStatus.CREATED, summary, note=note)


def _apply(
    batch: ImportBatch,
    parsed: ParsedCharacter,
    raw: dict,
    character: Character,
    status: str,
    summary: dict[str, int],
    note: str = "",
) -> CharacterSnapshot:
    character.level = parsed.level
    character.surname = parsed.surname or character.surname
    character.realm = parsed.realm
    character.guid = parsed.guid
    character.source = CharacterSource.ADDON
    character.last_synced_at = parsed.exported_at
    character.save(
        update_fields=["level", "surname", "realm", "guid", "source", "last_synced_at", "updated_at"]
    )
    summary["new_recipes"] += _apply_professions(character, raw.get("professions"))

    snapshot = _snapshot(batch, parsed, raw, character=character, status=status, note=note)
    CharacterSnapshot.objects.filter(
        character=character, day=snapshot.day, status__in=[SnapshotStatus.APPLIED, SnapshotStatus.CREATED]
    ).exclude(pk=snapshot.pk).delete()
    CharacterSnapshot.objects.filter(
        character=character, day__lt=snapshot.day - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    ).delete()
    return snapshot


def _apply_professions(character: Character, professions) -> int:
    """Remplace les métiers par ceux du jeu ; les recettes ne bougent que si la liste du métier a été lue."""
    if not isinstance(professions, list):
        return 0
    new_recipes = 0
    kept: list[int] = []
    for entry in professions:
        if not isinstance(entry, dict):
            continue
        slug = SKILL_LINES.get(entry.get("id")) if isinstance(entry.get("id"), int) else None
        slug = slug or (str(entry.get("slug") or "").strip() or None)
        profession = Profession.objects.filter(slug=slug).first() if slug else None
        if profession is None:
            continue
        skill = entry.get("skill")
        skill = max(1, min(int(skill), Profession.MAX_SKILL)) if isinstance(skill, int) else 1
        CharacterProfession.objects.update_or_create(
            character=character, profession=profession, defaults={"skill": skill}
        )
        kept.append(profession.pk)
        recipes = entry.get("recipes")
        if isinstance(recipes, list):
            wanted = set(
                Recipe.objects.filter(
                    profession=profession, id__in=[r for r in recipes if isinstance(r, int)]
                ).values_list("id", flat=True)
            )
            current = set(
                KnownRecipe.objects.filter(character=character, recipe__profession=profession).values_list(
                    "recipe_id", flat=True
                )
            )
            KnownRecipe.objects.filter(character=character, recipe_id__in=current - wanted).delete()
            KnownRecipe.objects.bulk_create(
                [KnownRecipe(character=character, recipe_id=rid) for rid in wanted - current]
            )
            new_recipes += len(wanted - current)
    CharacterProfession.objects.filter(character=character).exclude(profession_id__in=kept).delete()
    KnownRecipe.objects.filter(character=character).exclude(recipe__profession_id__in=kept).delete()
    return new_recipes


# --- résolution des personnages en attente ----------------------------------------------------


RESOLVABLE = {SnapshotStatus.PENDING, SnapshotStatus.IGNORED}


@transaction.atomic
def resolve_snapshot(
    snapshot: CharacterSnapshot, action: str, character: Character | None = None
) -> CharacterSnapshot:
    """merge : fusionne avec un personnage du site ; create : crée ; ignore : n'en parle plus."""
    if snapshot.status not in RESOLVABLE:
        raise ExportError("Ce personnage n'a rien à résoudre.")
    user = snapshot.user
    parsed = parse_character(snapshot.data)
    summary = {s: 0 for s in SnapshotStatus.values} | {"new_recipes": 0}
    if action == "ignore":
        IgnoredCharacter.objects.get_or_create(user=user, guid=parsed.guid, defaults={"name": parsed.name})
        snapshot.status = SnapshotStatus.IGNORED
        snapshot.note = "Ignoré à ta demande"
        snapshot.save(update_fields=["status", "note"])
        return snapshot
    if action == "merge":
        target = character or snapshot.candidate
        if target is None or target.owner_id != user.pk:
            raise ExportError("Choisis un de tes personnages pour la fusion.")
        if target.guid and target.guid != parsed.guid:
            raise ExportError(f"« {target.name} » est déjà rattaché à un autre personnage du jeu.")
        result = _apply(
            snapshot.batch,
            parsed,
            snapshot.data,
            target,
            SnapshotStatus.APPLIED,
            summary,
            note="Fusionné à ta demande",
        )
    elif action == "create":
        IgnoredCharacter.objects.filter(user=user, guid=parsed.guid).delete()
        result = _create(snapshot.batch, parsed, snapshot.data, summary, note="Créé à ta demande")
    else:
        raise ExportError("Action inconnue.")
    snapshot.delete()
    character_services.ensure_owner_has_main(user)
    return result


def pending_snapshots(user):
    """Dernier instantané par personnage du jeu encore à rattacher ou ignoré faute de niveau."""
    seen: set[str] = set()
    result = []
    queryset = (
        CharacterSnapshot.objects.filter(user=user, status__in=RESOLVABLE)
        .exclude(status=SnapshotStatus.IGNORED, note__startswith="Ignoré")
        .select_related("candidate")
        .order_by("-exported_at")
    )
    for snapshot in queryset:
        if snapshot.guid in seen or Character.objects.filter(guid=snapshot.guid).exists():
            continue
        seen.add(snapshot.guid)
        result.append(snapshot)
    return result


# --- dernière release du compagnon --------------------------------------------------------------


RELEASE_CACHE_KEY = "gamesync:latest_release"
RELEASE_TAG_PREFIX = "companion-v"


def latest_release(force: bool = False) -> dict | None:
    """Dernière release GitHub « companion-vX.Y.Z » (cache d'une heure) ; None sans release ou hors ligne."""
    import httpx

    if not force:
        cached = cache.get(RELEASE_CACHE_KEY)
        if cached is not None:
            return cached or None
    release = None
    try:
        response = httpx.get(
            f"https://api.github.com/repos/{settings.COMPANION_RELEASES_REPO}/releases",
            params={"per_page": 20},
            headers={"Accept": "application/vnd.github+json"},
            timeout=5,
        )
        if response.status_code == 200:
            for item in response.json():
                tag = item.get("tag_name", "")
                if item.get("draft") or item.get("prerelease") or not tag.startswith(RELEASE_TAG_PREFIX):
                    continue
                assets: dict[str, str] = {}
                for asset in item.get("assets", []):
                    name = asset.get("name", "").lower()
                    url = asset.get("browser_download_url")
                    if "addon" in name and name.endswith(".zip"):
                        assets["addon"] = url
                    elif name.endswith(".exe") or (name.endswith(".msi") and "windows" not in assets):
                        assets["windows"] = url  # l'installeur exe (NSIS) a la priorité sur le msi
                    elif name.endswith(".dmg"):
                        assets["macos"] = url
                release = {
                    "version": tag[len(RELEASE_TAG_PREFIX) :],
                    "tag": tag,
                    "published_at": item.get("published_at"),
                    "url": item.get("html_url"),
                    "assets": assets,
                }
                break
    except httpx.HTTPError:
        logger.warning("Impossible de lire les releases GitHub du compagnon", exc_info=True)
    cache.set(RELEASE_CACHE_KEY, release or False, 3600)
    return release
