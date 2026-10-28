"""
Format d'échange entre l'addon et le site (cahier des charges, étape 11).

Un code d'export : ``WFG<version>:<adler32 du JSON, 8 hex>:<base64 du JSON compressé en DEFLATE brut>``.
Le préfixe permet de refuser proprement un format inconnu ; la somme de contrôle détecte un code tronqué
à la copie.
L'encodeur sert aux tests et aux fixtures ; l'addon (Lua) produit exactement le même format.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import zlib

PREFIX = "WFG"
FORMAT_VERSION = 1
MAX_CODE_LENGTH = 256 * 1024

_CODE_RE = re.compile(r"^WFG(?P<version>\d+):(?P<checksum>[0-9a-f]{8}):(?P<data>[A-Za-z0-9+/=]+)$")


class ExportError(ValueError):
    """Erreur lisible par le joueur (code illisible, tronqué, version inconnue…)."""


def encode_export(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    compressor = zlib.compressobj(level=9, wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    checksum = zlib.adler32(raw) & 0xFFFFFFFF
    return f"{PREFIX}{FORMAT_VERSION}:{checksum:08x}:{base64.b64encode(compressed).decode()}"


def decode_export(code: str) -> dict:
    cleaned = "".join(code.split())  # le collage ajoute souvent des retours à la ligne
    if len(cleaned) > MAX_CODE_LENGTH:
        raise ExportError("Ce code est trop long pour être un export de l'addon.")
    match = _CODE_RE.match(cleaned)
    if not match:
        if cleaned.startswith(PREFIX):
            raise ExportError(
                "Code incomplet ou altéré : recopie-le entièrement depuis la fenêtre de l'addon."
            )
        raise ExportError("Ce texte n'est pas un code d'export de l'addon (il doit commencer par « WFG »).")
    version = int(match["version"])
    if version != FORMAT_VERSION:
        if version > FORMAT_VERSION:
            raise ExportError(
                "Ce code vient d'une version de l'addon plus récente que le site : réessaie plus tard."
            )
        raise ExportError("Ce code vient d'une ancienne version de l'addon : mets l'addon à jour.")
    try:
        compressed = base64.b64decode(match["data"], validate=True)
        raw = zlib.decompress(compressed, wbits=-15)
    except (binascii.Error, zlib.error) as exc:
        raise ExportError(
            "Code incomplet ou altéré : recopie-le entièrement depuis la fenêtre de l'addon."
        ) from exc
    if (zlib.adler32(raw) & 0xFFFFFFFF) != int(match["checksum"], 16):
        raise ExportError("Code incomplet : la somme de contrôle ne correspond pas, recopie-le.")
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise ExportError("Code illisible : contenu inattendu.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("characters"), list):
        raise ExportError("Code illisible : aucun personnage dedans.")
    return payload
