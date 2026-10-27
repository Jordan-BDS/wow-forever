"""Client minimal de l'API Discord (OAuth2 + lecture d'un membre via le token du bot)."""

from urllib.parse import urlencode

import httpx
from django.conf import settings

from apps.guild.config import discord_config

OAUTH_SCOPES = "identify"
TIMEOUT = 10.0


class DiscordError(Exception):
    pass


def redirect_uri() -> str:
    return f"{settings.SITE_URL}/api/auth/discord/callback/"


def authorize_url(state: str) -> str:
    params = {
        "client_id": discord_config().client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "scope": OAUTH_SCOPES,
        "state": state,
        "prompt": "none",
    }
    return f"{settings.DISCORD_API_BASE}/oauth2/authorize?{urlencode(params)}"


def _check(response: httpx.Response) -> dict:
    if response.is_error:
        raise DiscordError(f"Discord a répondu {response.status_code} : {response.text[:200]}")
    return response.json()


def exchange_code(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
    }
    config = discord_config()
    auth = (config.client_id, config.client_secret)
    try:
        response = httpx.post(
            f"{settings.DISCORD_API_BASE}/oauth2/token", data=data, auth=auth, timeout=TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise DiscordError(str(exc)) from exc
    return _check(response)


def fetch_me(access_token: str) -> dict:
    try:
        response = httpx.get(
            f"{settings.DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise DiscordError(str(exc)) from exc
    return _check(response)


def fetch_guild_member(user_id: str) -> dict | None:
    """Profil de membre sur le serveur de la guilde, ou None s'il n'en fait pas partie."""
    config = discord_config()
    try:
        response = httpx.get(
            f"{settings.DISCORD_API_BASE}/guilds/{config.guild_id}/members/{user_id}",
            headers={"Authorization": f"Bot {config.bot_token}"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise DiscordError(str(exc)) from exc
    if response.status_code == 404:
        return None
    return _check(response)
