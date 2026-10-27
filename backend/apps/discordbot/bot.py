"""
Bot Discord de la guilde : dépile l'outbox de notifications, envoie les rappels,
coupe l'accès des membres qui perdent le rôle, et expose quelques commandes slash.

discord.py est asynchrone et l'ORM Django synchrone : tout accès base passe par `sync_to_async`.
"""

import logging

import discord
from asgiref.sync import sync_to_async
from discord import app_commands
from discord.ext import commands, tasks
from django.conf import settings

from apps.notifications.reminders import scan_due_reminders

from . import services

logger = logging.getLogger(__name__)

db = sync_to_async  # lisibilité : `await db(fonction)(args)`

ROLE_CHOICES = [
    app_commands.Choice(name="Tank", value="tank"),
    app_commands.Choice(name="Heal", value="heal"),
    app_commands.Choice(name="DPS", value="dps"),
]
STATUS_CHOICES = [
    app_commands.Choice(name="Présent", value="present"),
    app_commands.Choice(name="Peut-être", value="maybe"),
    app_commands.Choice(name="En retard", value="late"),
    app_commands.Choice(name="Absent", value="absent"),
]


class GuildBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # intent privilégié « Server Members », à activer dans le portail développeur
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.guild_object = discord.Object(id=int(settings.DISCORD_GUILD_ID))

    async def setup_hook(self) -> None:
        self.tree.add_command(events_command, guild=self.guild_object)
        self.tree.add_command(signup_command, guild=self.guild_object)
        self.tree.add_command(craft_command, guild=self.guild_object)
        await self.tree.sync(guild=self.guild_object)
        self.dispatch_outbox.start()
        self.scan_reminders.start()

    async def on_ready(self) -> None:
        logger.info("Bot connecté en tant que %s", self.user)

    # --- outbox -------------------------------------------------------------------

    @tasks.loop(seconds=10)
    async def dispatch_outbox(self) -> None:
        for notification in await db(services.pending_notifications)():
            try:
                if notification.is_dm:
                    user = await self.fetch_user(int(notification.recipient.discord_id))
                    await user.send(notification.text)
                else:
                    channel_id = await db(services.announcement_channel_id)()
                    if channel_id is None:
                        await db(services.mark_skipped)(notification, "Aucun salon d'annonces configuré.")
                        continue
                    channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
                    await channel.send(notification.text)
                await db(services.mark_sent)(notification)
            except discord.Forbidden as exc:
                await db(services.mark_skipped)(notification, f"Envoi refusé par Discord : {exc}")
            except Exception as exc:  # noqa: BLE001 — on journalise et on réessaie plus tard
                await db(services.mark_failed)(notification, repr(exc))

    @dispatch_outbox.before_loop
    async def _wait_outbox(self) -> None:
        await self.wait_until_ready()

    # --- rappels ------------------------------------------------------------------

    @tasks.loop(seconds=60)
    async def scan_reminders(self) -> None:
        try:
            created = await db(scan_due_reminders)()
            if created:
                logger.info("%s rappel(s) mis en file", created)
        except Exception:  # noqa: BLE001
            logger.exception("Échec du balayage des rappels")

    @scan_reminders.before_loop
    async def _wait_reminders(self) -> None:
        await self.wait_until_ready()

    # --- révocation d'accès ------------------------------------------------------

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.guild.id != self.guild_object.id:
            return
        had = services.has_allowed_role([str(r.id) for r in before.roles])
        has = services.has_allowed_role([str(r.id) for r in after.roles])
        if had and not has:
            await db(services.revoke_access)(str(after.id), "rôle Discord retiré")

    async def on_member_remove(self, member: discord.Member) -> None:
        if member.guild.id == self.guild_object.id:
            await db(services.revoke_access)(str(member.id), "a quitté le serveur")


# --- commandes slash ----------------------------------------------------------------


@app_commands.command(name="events", description="Les prochains événements de la guilde")
async def events_command(interaction: discord.Interaction) -> None:
    text = await db(services.upcoming_events_text)()
    await interaction.response.send_message(text, ephemeral=True)


@app_commands.command(name="inscription", description="S'inscrire à un événement avec un de ses personnages")
@app_commands.describe(
    evenement="L'événement", personnage="Ton personnage", role="Ton rôle", statut="Ta présence"
)
@app_commands.choices(role=ROLE_CHOICES, statut=STATUS_CHOICES)
async def signup_command(
    interaction: discord.Interaction,
    evenement: int,
    personnage: int,
    role: app_commands.Choice[str],
    statut: app_commands.Choice[str] | None = None,
) -> None:
    message = await db(services.signup_from_discord)(
        str(interaction.user.id), evenement, personnage, role.value, statut.value if statut else "present"
    )
    await interaction.response.send_message(message, ephemeral=True)


@signup_command.autocomplete("evenement")
async def _event_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    return [
        app_commands.Choice(name=label, value=pk) for label, pk in await db(services.event_choices)(current)
    ]


@signup_command.autocomplete("personnage")
async def _character_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    choices = await db(services.character_choices)(str(interaction.user.id), current)
    return [app_commands.Choice(name=label, value=pk) for label, pk in choices]


@app_commands.command(name="craft", description="Qui sait crafter quoi ?")
@app_commands.describe(recherche="Nom de recette ou d'objet")
async def craft_command(interaction: discord.Interaction, recherche: str) -> None:
    text = await db(services.craft_search_text)(recherche)
    await interaction.response.send_message(text, ephemeral=True)


def run() -> None:
    if not settings.DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN manquant.")
    GuildBot().run(settings.DISCORD_BOT_TOKEN, log_handler=None)
