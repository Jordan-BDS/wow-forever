"""Téléchargement des exports CSV de wago.tools (tables DB2 du client)."""

import json
import logging
from pathlib import Path

import httpx

from .importer import FALLBACK_TABLES, TABLES, TRAIT_TABLES

logger = logging.getLogger(__name__)

API = "https://wago.tools"
DEFAULT_PRODUCT = "wowf"  # WoW Forever ; « wow_classic_era » en secours
FALLBACK_PRODUCT = "wow_classic_era"  # fiches des objets que la table de Forever n'a pas
TIMEOUT = 300.0


def latest_build(product: str) -> str:
    response = httpx.get(f"{API}/api/builds", timeout=60.0)
    response.raise_for_status()
    builds = response.json()
    if product not in builds or not builds[product]:
        raise ValueError(f"Produit inconnu sur wago.tools : {product} (connus : {', '.join(sorted(builds))})")
    return builds[product][0]["version"]


def download_tables(build: str, directory: Path, force: bool = False) -> list[str]:
    """Télécharge les tables manquantes dans `directory`. Renvoie la liste des fichiers téléchargés."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    downloaded = []
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for table in TABLES + TRAIT_TABLES:
            target = directory / f"{table}.csv"
            if target.exists() and not force:
                continue
            name, _, locale = table.partition(".")
            params = {"build": build, "locale": locale or "frFR"}
            logger.info("Téléchargement %s (%s)", name, params["locale"])
            response = client.get(f"{API}/db2/{name}/csv", params=params)
            if table in TRAIT_TABLES and response.status_code in (400, 404):
                logger.info("Table %s absente de ce client : talents lus dans la table Talent", name)
                continue
            response.raise_for_status()
            target.write_text(response.text, encoding="utf-8")
            downloaded.append(table)
    (directory / "build.json").write_text(json.dumps({"build": build}), encoding="utf-8")
    return downloaded


def download_fallback_tables(directory: Path, force: bool = False) -> list[str]:
    """Télécharge les fiches d'objets de secours (dernier Classic Era) manquantes dans `directory`."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    wanted = [t for t in FALLBACK_TABLES if force or not (directory / f"{t}.csv").exists()]
    if not wanted:
        return []
    build = latest_build(FALLBACK_PRODUCT)
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for table in wanted:
            # « Fallback.ItemSparse.enUS » : table ItemSparse, en anglais ; sans suffixe, en français.
            _, name, locale = (table.split(".") + [""])[:3]
            logger.info("Téléchargement %s (%s, %s %s)", name, locale or "frFR", FALLBACK_PRODUCT, build)
            response = client.get(
                f"{API}/db2/{name}/csv", params={"build": build, "locale": locale or "frFR"}
            )
            response.raise_for_status()
            (directory / f"{table}.csv").write_text(response.text, encoding="utf-8")
    return wanted
