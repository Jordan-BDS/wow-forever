"""
Configuration Discord effective : les paramètres saisis par le GM sur le site priment, les variables
d'environnement servent de secours (premier démarrage, avant qu'un GM puisse se connecter).
"""

from dataclasses import dataclass

from django.conf import settings

from .models import GuildSettings


@dataclass(frozen=True)
class DiscordConfig:
    client_id: str
    client_secret: str
    bot_token: str
    guild_id: str
    allowed_role_ids: list[str]
    first_gm_id: str

    @property
    def login_ready(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.bot_token
            and self.guild_id
            and self.allowed_role_ids
        )


def discord_config() -> DiscordConfig:
    stored = GuildSettings.load()
    role_ids = [r.strip() for r in (stored.discord_allowed_role_ids or "").split(",") if r.strip()]
    return DiscordConfig(
        client_id=stored.discord_client_id or settings.DISCORD_CLIENT_ID,
        client_secret=stored.discord_client_secret or settings.DISCORD_CLIENT_SECRET,
        bot_token=stored.discord_bot_token or settings.DISCORD_BOT_TOKEN,
        guild_id=stored.discord_guild_id or settings.DISCORD_GUILD_ID,
        allowed_role_ids=role_ids or list(settings.DISCORD_ALLOWED_ROLE_IDS),
        first_gm_id=stored.discord_first_gm_id or settings.DISCORD_FIRST_GM_ID,
    )
