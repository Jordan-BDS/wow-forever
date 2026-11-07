"""
Client minimal de l'API Battle.net pour WoW Forever. L'API n'est pas documentée par Blizzard (novembre 2026) :
les espaces de noms `profile-forever-{région}`, `dynamic-forever-{région}` et
`static-{version}-forever-{région}` viennent des sondes de la communauté, et les personnages s'adressent sans
royaume, par `prénom-nom` en minuscules. Jeton d'application (client credentials), suffisant pour les
personnages et la guilde.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OAUTH_URL = "https://oauth.battle.net/token"
GAME = "forever"
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


class BlizzardError(Exception):
    """Réponse inattendue de l'API (hors 404, qui est une absence de donnée, pas une erreur)."""


class BlizzardClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        region: str = "eu",
        locale: str = "fr_FR",
        static_version: str = "",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not client_id or not client_secret:
            raise BlizzardError("BLIZZARD_CLIENT_ID et BLIZZARD_CLIENT_SECRET sont vides (deploy/.env)")
        self.client_id = client_id
        self.client_secret = client_secret
        self.region = region.lower()
        self.locale = locale
        self.static_version = static_version
        self.sleep = sleep
        self.http = httpx.Client(timeout=30.0, transport=transport)
        self.calls = 0
        self._token: str | None = None
        self._expires_at = 0.0

    @property
    def base_url(self) -> str:
        return f"https://{self.region}.api.blizzard.com"

    def namespace(self, kind: str) -> str:
        """`profile`, `dynamic` ou `static` → espace de noms Forever de la région (le statique peut exiger sa
        version, ex. `static-1.60.1_70399-forever-eu` ; sans version le serveur répondait 403 avant la
        sortie)."""
        if kind == "static" and self.static_version:
            return f"static-{self.static_version}-{GAME}-{self.region}"
        return f"{kind}-{GAME}-{self.region}"

    def token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        response = self.http.post(
            OAUTH_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
        )
        if response.status_code != 200:
            raise BlizzardError(
                f"jeton refusé ({response.status_code}) : identifiants Battle.net invalides ?"
            )
        payload = response.json()
        self._token = str(payload["access_token"])
        self._expires_at = time.time() + float(payload.get("expires_in", 3600))
        return self._token

    def get(self, path: str, kind: str = "profile", params: dict[str, Any] | None = None) -> tuple[int, Any]:
        """(statut, JSON). 404 → (404, None) : la ressource n'existe pas (personnage jamais déconnecté,
        niveau < 10, route absente). 429 et 5xx : nouvelles tentatives avec attente. Le reste est une
        erreur."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        query = {"namespace": self.namespace(kind), "locale": self.locale, **(params or {})}
        for attempt in range(MAX_ATTEMPTS):
            self.calls += 1
            response = self.http.get(url, params=query, headers={"Authorization": f"Bearer {self.token()}"})
            if response.status_code == 401 and attempt == 0:
                self._token = None  # jeton expiré côté serveur : on en reprend un
                continue
            if response.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS - 1:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else float(2**attempt)
                logger.warning(
                    "Battle.net %s sur %s : nouvelle tentative dans %.0f s", response.status_code, path, delay
                )
                self.sleep(delay)
                continue
            if response.status_code == 404:
                return 404, None
            if response.status_code >= 400:
                raise BlizzardError(f"{response.status_code} sur {path} : {response.text[:200]}")
            return response.status_code, response.json()
        raise BlizzardError(f"trop de tentatives sur {path}")

    # --- routes Forever ---------------------------------------------------------------------------------

    def character(self, slug: str, resource: str = "") -> tuple[int, Any]:
        """Fiche d'un personnage (`prénom-nom`) ou une de ses sous-ressources (`equipment`, `statistics`…)."""
        path = f"profile/wow/character/{slug}"
        if resource:
            path += f"/{resource}"
        return self.get(path, "profile")

    def guild(self, slug: str, resource: str = "") -> tuple[int, Any]:
        """Guilde (`nom-de-guilde`) ou une de ses sous-ressources (`roster`, `activity`, `achievements`)."""
        path = f"data/wow/guild/{slug}"
        if resource:
            path += f"/{resource}"
        return self.get(path, "profile")

    def rulesets(self) -> tuple[int, Any]:
        return self.get("data/wow/ruleset/index", "dynamic")

    def playable_classes(self) -> tuple[int, Any]:
        return self.get("data/wow/playable-class/index", "static")
