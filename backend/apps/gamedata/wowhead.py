"""
Fiches des objets que ni la table de Forever ni celle de Classic Era ne décrivent : le serveur de Forever les
envoie au client en jeu, aucune table téléchargeable ne les contient (surtout des armures et des armes
ajoutées par Forever). Wowhead les connaît : son service d'infobulles, celui qu'interroge déjà la page pour
afficher une infobulle, donne le nom, la qualité, l'icône, les niveaux et les statistiques.

Ce n'est pas une API publiée : tout échec est sans gravité, l'import se fait alors sans ces fiches et les
objets restent affichés « Objet 282550 ». Les fiches lues sont gardées dans `Wowhead.Items.csv`, à côté des
tables du client, et ne sont pas redemandées ; les objets que Wowhead ne connaît pas non plus y ont une ligne
sans nom, pour la même raison.
"""

import csv
import json
import logging
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

API = "https://nether.wowhead.com/forever/tooltip/item"
TABLE = "Wowhead.Items"
FIELDS = ["ID", "Name_fr", "Name_en", "Quality", "Icon", "ItemLevel", "RequiredLevel", "Stats"]
TIMEOUT = 30.0
DELAY = 0.05  # s entre deux objets : on ne presse pas un service qu'on ne nous doit pas
MAX_FAILURES = 10  # échecs d'affilée avant d'abandonner (service en panne, ou qui nous refuse)
SAVE_EVERY = 200  # objets lus entre deux écritures du fichier : un arrêt en route ne perd pas tout

ITEM_LEVEL = re.compile(r"<!--ilvl-->(\d+)")
REQUIRED_LEVEL = re.compile(r"<!--rlvl-->(\d+)")
STAT = re.compile(r"<!--stat(\d+)-->\s*([+-]\d+)")


class WowheadError(Exception):
    """Le service ne répond plus comme attendu : on s'arrête, ce qui a été lu est gardé."""


def clean_name(value) -> str:
    """Le nom d'une infobulle. Un nom entre crochets est un nom que Wowhead n'a pas dans cette langue (il
    montre alors l'anglais entre crochets) : pas de nom."""
    name = " ".join(value.split()) if isinstance(value, str) else ""
    return "" if name.startswith("[") and name.endswith("]") else name


def parse(payload: dict) -> dict:
    """Ce qu'une infobulle dit d'un objet, dans la langue demandée."""
    tooltip = payload.get("tooltip") if isinstance(payload.get("tooltip"), str) else ""
    quality = payload.get("quality")
    level, required = ITEM_LEVEL.search(tooltip), REQUIRED_LEVEL.search(tooltip)
    stats: dict[str, int] = {}
    for stat_type, amount in STAT.findall(tooltip):
        stats[stat_type] = stats.get(stat_type, 0) + int(amount)
    return {
        "name": clean_name(payload.get("name")),
        "quality": quality if isinstance(quality, int) and not isinstance(quality, bool) else 1,
        "icon": payload.get("icon").lower() if isinstance(payload.get("icon"), str) else "",
        "item_level": int(level.group(1)) if level else 1,
        "required_level": int(required.group(1)) if required else 0,
        "stats": stats,
    }


def fetch(client: httpx.Client, item_id: int, locale: str) -> dict | None:
    """L'infobulle d'un objet dans une langue. None si Wowhead ne connaît pas l'objet."""
    response = client.get(f"{API}/{item_id}", params={"locale": locale})
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise WowheadError(f"réponse inattendue pour l'objet {item_id}")
    return parse(payload)


def fetch_item(client: httpx.Client, item_id: int) -> dict | None:
    """La ligne d'un objet pour `Wowhead.Items.csv`. None s'il est inconnu ou n'a pas de nom anglais."""
    english = fetch(client, item_id, "enUS")
    if english is None or not english["name"]:
        return None
    french = fetch(client, item_id, "frFR")
    return {
        "ID": str(item_id),
        # Pas encore traduit : le nom anglais, comme le montre le jeu.
        "Name_fr": (french["name"] if french else "") or english["name"],
        "Name_en": english["name"],
        "Quality": str(english["quality"]),
        "Icon": english["icon"],
        "ItemLevel": str(english["item_level"]),
        "RequiredLevel": str(english["required_level"]),
        "Stats": json.dumps(english["stats"], sort_keys=True),
    }


def read_rows(directory: Path) -> dict[int, dict]:
    path = Path(directory) / f"{TABLE}.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {int(row["ID"]): row for row in csv.DictReader(handle) if row.get("ID", "").isdigit()}


def write_rows(directory: Path, rows: dict[int, dict]) -> None:
    path = Path(directory) / f"{TABLE}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item_id in sorted(rows):
            writer.writerow(rows[item_id])


def download_items(
    directory: Path,
    item_ids: Iterable[int],
    *,
    force: bool = False,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Lit sur Wowhead les fiches des objets demandés qui ne sont pas déjà dans `Wowhead.Items.csv` (toutes
    avec `force`) et les y ajoute. Un objet que Wowhead ne connaît pas y est noté aussi, sans nom : il n'est
    plus redemandé, sauf avec `force`. Renvoie le nombre de fiches ajoutées. `WowheadError` après
    `MAX_FAILURES` échecs d'affilée : ce qui a été lu avant est écrit."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = read_rows(directory)
    wanted = sorted(set(item_ids) if force else set(item_ids) - set(rows))
    if not wanted:
        return 0
    added = done = failures = 0
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True, transport=transport) as client:
            for item_id in wanted:
                try:
                    row = fetch_item(client, item_id)
                except (httpx.HTTPError, ValueError, WowheadError) as error:
                    failures += 1
                    logger.warning("Wowhead : objet %s illisible (%s)", item_id, error)
                    if failures >= MAX_FAILURES:
                        raise WowheadError(
                            f"{failures} échecs d'affilée, abandon à l'objet {item_id}"
                        ) from error
                    continue
                failures = 0
                # Inconnu de Wowhead : une ligne sans nom, pour ne pas le redemander à chaque import.
                rows[item_id] = row or {"ID": str(item_id)}
                added += row is not None
                done += 1
                if done % SAVE_EVERY == 0:
                    write_rows(directory, rows)
                sleep(DELAY)
    finally:
        write_rows(directory, rows)
    return added
