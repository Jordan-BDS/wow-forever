"""
Prépare le serveur Discord : crée les rôles du site s'ils manquent, donne le rôle « Membre » à tous les
humains présents, et enregistre les IDs dans Guilde › Paramètres (rôles autorisés à se connecter).

Prérequis : le bot invité sur le serveur avec la permission « Gérer les rôles », et l'intent privilégié
« Server Members » activé sur l'application (nécessaire pour lister les membres).
"""

import time

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.guild.config import discord_config
from apps.guild.models import GuildSettings

MANAGE_ROLES = 0x10000000
VIEW_CHANNEL = 0x400
SEND_MESSAGES = 0x800
BOT_PERMISSIONS = MANAGE_ROLES | VIEW_CHANNEL | SEND_MESSAGES


class DiscordClient:
    def __init__(self, token: str):
        self.http = httpx.Client(
            base_url=settings.DISCORD_API_BASE, headers={"Authorization": f"Bot {token}"}, timeout=30.0
        )

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Appel avec respect des limites de débit (429 → attente puis nouvel essai)."""
        for _ in range(5):
            response = self.http.request(method, path, **kwargs)
            if response.status_code != 429:
                return response
            time.sleep(float(response.headers.get("Retry-After", "1")) + 0.2)
        return response

    def roles(self, guild_id: str) -> list[dict]:
        response = self.request("GET", f"/guilds/{guild_id}/roles")
        self._check(response, "lecture des rôles")
        return response.json()

    def create_role(self, guild_id: str, name: str, color: int) -> dict:
        response = self.request(
            "POST",
            f"/guilds/{guild_id}/roles",
            json={"name": name, "color": color, "hoist": False, "mentionable": True},
        )
        self._check(response, f"création du rôle {name}")
        return response.json()

    def members(self, guild_id: str) -> list[dict]:
        members: list[dict] = []
        after = "0"
        while True:
            response = self.request(
                "GET", f"/guilds/{guild_id}/members", params={"limit": 1000, "after": after}
            )
            self._check(response, "liste des membres (intent « Server Members » activé ?)")
            page = response.json()
            members.extend(page)
            if len(page) < 1000:
                return members
            after = page[-1]["user"]["id"]

    def add_role(self, guild_id: str, user_id: str, role_id: str) -> None:
        response = self.request("PUT", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")
        self._check(response, f"attribution du rôle à {user_id}")

    @staticmethod
    def _check(response: httpx.Response, what: str) -> None:
        if response.is_error:
            raise CommandError(
                f"Échec : {what} → Discord a répondu {response.status_code} : {response.text[:200]}"
            )


class Command(BaseCommand):
    help = "Crée les rôles Membre / Officier sur le serveur Discord et donne Membre à tout le monde."

    def add_arguments(self, parser):
        parser.add_argument("--member-name", default="Membre")
        parser.add_argument("--officer-name", default="Officier")
        parser.add_argument(
            "--dry-run", action="store_true", help="Montre ce qui serait fait sans rien changer"
        )
        parser.add_argument(
            "--no-assign", action="store_true", help="Ne pas donner le rôle Membre aux membres"
        )
        parser.add_argument(
            "--no-save", action="store_true", help="Ne pas enregistrer les IDs dans les paramètres"
        )

    def handle(self, *args, **options):
        config = discord_config()
        if not config.bot_token or not config.guild_id:
            raise CommandError("Token du bot et ID du serveur requis (Guilde › Paramètres ou backend/.env).")
        if config.client_id:
            invite = (
                f"https://discord.com/oauth2/authorize?client_id={config.client_id}"
                f"&scope=bot%20applications.commands&permissions={BOT_PERMISSIONS}"
            )
            self.stdout.write(f"Lien d'invitation du bot (si pas encore fait) : {invite}")

        client = DiscordClient(config.bot_token)
        dry = options["dry_run"]
        existing = {role["name"].casefold(): role for role in client.roles(config.guild_id)}

        wanted = {options["member_name"]: 0x2B5BB0, options["officer_name"]: 0xD9B84A}
        ids: dict[str, str] = {}
        for name, color in wanted.items():
            role = existing.get(name.casefold())
            if role:
                self.stdout.write(f"Rôle « {role['name']} » déjà présent (ID {role['id']}).")
            elif dry:
                self.stdout.write(f"[dry-run] Créerait le rôle « {name} ».")
                continue
            else:
                role = client.create_role(config.guild_id, name, color)
                self.stdout.write(self.style.SUCCESS(f"Rôle « {name} » créé (ID {role['id']})."))
            ids[name] = role["id"]

        member_role_id = ids.get(options["member_name"])
        if not options["no_assign"]:
            members = client.members(config.guild_id)
            humans = [m for m in members if not m["user"].get("bot")]
            todo = [m for m in humans if member_role_id not in m.get("roles", [])]
            self.stdout.write(f"{len(humans)} humain(s) sur le serveur, {len(todo)} sans le rôle Membre.")
            for member in todo:
                label = member.get("nick") or member["user"].get("global_name") or member["user"]["username"]
                if dry or member_role_id is None:
                    self.stdout.write(f"[dry-run] Donnerait Membre à {label}")
                else:
                    client.add_role(config.guild_id, member["user"]["id"], member_role_id)
                    self.stdout.write(f"  Membre → {label}")

        if not options["no_save"] and not dry and ids:
            stored = GuildSettings.load()
            allowed = {r for r in stored.discord_allowed_role_ids.split(",") if r} | set(ids.values())
            stored.discord_allowed_role_ids = ",".join(sorted(allowed))
            if not stored.discord_guild_id:
                stored.discord_guild_id = config.guild_id
            stored.save()
            self.stdout.write(
                self.style.SUCCESS(f"Rôles autorisés enregistrés : {stored.discord_allowed_role_ids}")
            )
        self.stdout.write("Terminé.")
