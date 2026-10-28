"""
Prépare les salons Discord liés au site : crée « agenda » et « demande-de-craft » s'ils manquent, en lecture
seule pour les membres (réactions et boutons autorisés, pas de messages), avec les droits nécessaires au bot
(envoyer, intégrer des liens). Enregistre les IDs dans Guilde › Paramètres, et retient le salon
« sondages » existant pour les sondages s'il y en a un.

Prérequis : le bot invité avec « Gérer les salons » et « Gérer les rôles » (indispensable pour poser des
permissions par salon). Rejouable sans effet si tout est déjà en place.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.guild.config import discord_config
from apps.guild.models import GuildSettings

from .discord_setup_roles import DiscordClient

TEXT_CHANNEL = 0
CATEGORY = 4
OVERWRITE_ROLE = 0
OVERWRITE_MEMBER = 1

VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
MANAGE_MESSAGES = 1 << 13
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
ADD_REACTIONS = 1 << 6
USE_APPLICATION_COMMANDS = 1 << 31
CREATE_PUBLIC_THREADS = 1 << 35
CREATE_PRIVATE_THREADS = 1 << 36
SEND_MESSAGES_IN_THREADS = 1 << 38

EVERYONE_ALLOW = VIEW_CHANNEL | READ_MESSAGE_HISTORY | ADD_REACTIONS | USE_APPLICATION_COMMANDS
EVERYONE_DENY = (
    SEND_MESSAGES | ATTACH_FILES | CREATE_PUBLIC_THREADS | CREATE_PRIVATE_THREADS | SEND_MESSAGES_IN_THREADS
)
BOT_ALLOW = VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES | MANAGE_MESSAGES | READ_MESSAGE_HISTORY

# (option de nom, champ de GuildSettings, sujet du salon)
MANAGED = [
    ("agenda_name", "discord_agenda_channel_id", "Événements de la guilde : inscris-toi avec les boutons."),
    ("crafts_name", "discord_crafts_channel_id", "Demandes de craft publiées depuis le site."),
]


def overwrites(guild_id: str, bot_user_id: str) -> list[dict]:
    return [
        {"id": guild_id, "type": OVERWRITE_ROLE, "allow": str(EVERYONE_ALLOW), "deny": str(EVERYONE_DENY)},
        {"id": bot_user_id, "type": OVERWRITE_MEMBER, "allow": str(BOT_ALLOW), "deny": "0"},
    ]


class Command(BaseCommand):
    help = "Crée les salons agenda et demande-de-craft (lecture seule) et les enregistre dans les paramètres."

    def add_arguments(self, parser):
        parser.add_argument("--agenda-name", default="agenda")
        parser.add_argument("--crafts-name", default="demande-de-craft")
        parser.add_argument(
            "--polls-name", default="sondages", help="Salon existant à utiliser pour les sondages"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Montre ce qui serait fait sans rien changer"
        )
        parser.add_argument(
            "--no-save", action="store_true", help="Ne pas enregistrer les IDs dans les paramètres"
        )

    def handle(self, *args, **options):
        config = discord_config()
        if not config.bot_token or not config.guild_id:
            raise CommandError("Token du bot et ID du serveur requis (Guilde › Paramètres ou backend/.env).")
        client = DiscordClient(config.bot_token)
        dry = options["dry_run"]

        bot_user_id = self._bot_user_id(client)
        channels = self._channels(client, config.guild_id)
        by_name = {c["name"].casefold(): c for c in channels if c["type"] == TEXT_CHANNEL}
        parent_id = self._text_category(channels)

        ids: dict[str, str] = {}
        for option, field, topic in MANAGED:
            name = options[option]
            channel = by_name.get(name.casefold())
            if channel:
                self.stdout.write(f"Salon « #{channel['name']} » déjà présent (ID {channel['id']}).")
                if not dry:
                    self._apply_overwrites(client, channel, config.guild_id, bot_user_id)
            elif dry:
                self.stdout.write(f"[dry-run] Créerait le salon « #{name} » en lecture seule.")
                continue
            else:
                channel = self._create(client, config.guild_id, name, topic, parent_id, bot_user_id)
                self.stdout.write(self.style.SUCCESS(f"Salon « #{name} » créé (ID {channel['id']})."))
            ids[field] = channel["id"]

        polls = by_name.get(options["polls_name"].casefold())
        if polls:
            self.stdout.write(f"Sondages : salon existant « #{polls['name']} » (ID {polls['id']}).")
            ids["discord_polls_channel_id"] = polls["id"]
        else:
            self.stdout.write(
                f"Pas de salon « #{options['polls_name']} » : les sondages iront au salon général."
            )

        if not options["no_save"] and not dry and ids:
            stored = GuildSettings.load()
            for field, value in ids.items():
                setattr(stored, field, value)
            stored.save()
            self.stdout.write(self.style.SUCCESS("Salons enregistrés dans Guilde › Paramètres."))
        self.stdout.write("Terminé.")

    # --- appels Discord ---------------------------------------------------------------

    def _bot_user_id(self, client: DiscordClient) -> str:
        response = client.request("GET", "/users/@me")
        client._check(response, "identité du bot")
        return response.json()["id"]

    def _channels(self, client: DiscordClient, guild_id: str) -> list[dict]:
        response = client.request("GET", f"/guilds/{guild_id}/channels")
        client._check(response, "liste des salons (permission « Voir les salons » ?)")
        return response.json()

    @staticmethod
    def _text_category(channels: list[dict]) -> str | None:
        """Catégorie où ranger les salons : celle du premier salon texte, sinon aucune."""
        for channel in sorted(channels, key=lambda c: c.get("position", 0)):
            if channel["type"] == TEXT_CHANNEL and channel.get("parent_id"):
                return channel["parent_id"]
        return None

    def _create(self, client, guild_id: str, name: str, topic: str, parent_id: str | None, bot_user_id: str):
        payload = {
            "name": name,
            "type": TEXT_CHANNEL,
            "topic": topic,
            "permission_overwrites": overwrites(guild_id, bot_user_id),
        }
        if parent_id:
            payload["parent_id"] = parent_id
        response = client.request("POST", f"/guilds/{guild_id}/channels", json=payload)
        if response.status_code == 403:
            raise CommandError(
                "Discord refuse (Missing Permissions) : le bot a besoin de « Gérer les salons » et "
                "« Gérer les rôles ». Regénère le lien d'invitation avec ces permissions et réinvite-le."
            )
        client._check(response, f"création du salon {name}")
        return response.json()

    def _apply_overwrites(self, client, channel: dict, guild_id: str, bot_user_id: str) -> None:
        """Salon déjà là (créé à la main ou commande rejouée) : on (ré)applique la lecture seule."""
        wanted = {o["id"]: o for o in overwrites(guild_id, bot_user_id)}
        current = {o["id"]: o for o in channel.get("permission_overwrites", [])}
        if all(current.get(k, {}).get("allow") == v["allow"] and current.get(k, {}).get("deny") == v["deny"]
               for k, v in wanted.items()):  # fmt: skip
            return
        response = client.request(
            "PATCH", f"/channels/{channel['id']}", json={"permission_overwrites": list(wanted.values())}
        )
        client._check(response, f"permissions du salon #{channel['name']}")
        self.stdout.write(f"  Permissions de « #{channel['name']} » mises à jour (lecture seule).")
