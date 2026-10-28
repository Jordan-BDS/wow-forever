"""
Bot Discord de la guilde : dépile l'outbox de notifications, envoie les rappels,
coupe l'accès des membres qui perdent le rôle, expose quelques commandes slash et tient
l'onglet « Événements » de Discord synchronisé avec l'agenda du site (dans les deux sens).

discord.py est asynchrone et l'ORM Django synchrone : tout accès base passe par `sync_to_async`.
"""

import logging

import discord
from asgiref.sync import sync_to_async
from discord import app_commands
from discord.ext import commands, tasks

from apps.guild.config import discord_config
from apps.notifications.models import NotificationKind
from apps.notifications.reminders import scan_due_reminders

from . import eventsync, services

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
        self.guild_object = discord.Object(id=int(discord_config().guild_id))

    async def setup_hook(self) -> None:
        self.tree.add_command(events_command, guild=self.guild_object)
        self.tree.add_command(signup_command, guild=self.guild_object)
        self.tree.add_command(craft_command, guild=self.guild_object)
        await self.tree.sync(guild=self.guild_object)
        self.add_dynamic_items(eventsync.SignupButton)  # boutons d'inscription des messages déjà publiés
        self.dispatch_outbox.start()
        self.scan_reminders.start()

    async def on_ready(self) -> None:
        logger.info("Bot connecté en tant que %s", self.user)

    # --- outbox -------------------------------------------------------------------

    @tasks.loop(seconds=10)
    async def dispatch_outbox(self) -> None:
        for notification in await db(services.pending_notifications)():
            try:
                if notification.kind == NotificationKind.EVENT_SYNC:
                    if notification.event_id is None:
                        await db(services.mark_skipped)(notification, "Événement supprimé.")
                        continue
                    await eventsync.sync_event(self, notification.event_id)
                    continue  # acquittée par sync_event
                if notification.kind == NotificationKind.POLL_SYNC:
                    if notification.poll_id is None:
                        await db(services.mark_skipped)(notification, "Sondage supprimé.")
                        continue
                    await eventsync.sync_poll(self, notification.poll_id)
                    continue  # acquittée par sync_poll
                if notification.kind == NotificationKind.DISCORD_CLEANUP:
                    await eventsync.cleanup_discord(self, notification.payload)
                    await db(services.mark_sent)(notification)
                    continue
                if notification.is_dm:
                    user = await self.fetch_user(int(notification.recipient.discord_id))
                    await user.send(notification.text)
                else:
                    channel_id = await db(services.channel_id_for)(notification.kind)
                    if channel_id is None:
                        await db(services.mark_skipped)(notification, "Aucun salon configuré pour ce type.")
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

    # --- onglet « Événements » de Discord → site -------------------------------------

    def _ours(self, scheduled: discord.ScheduledEvent) -> bool:
        return scheduled.guild_id == self.guild_object.id

    async def on_scheduled_event_create(self, scheduled: discord.ScheduledEvent) -> None:
        if not self._ours(scheduled) or scheduled.creator_id == self.user.id:
            return  # créé par le bot lui-même : déjà sur le site
        event = await db(services.create_event_from_discord)(
            scheduled.id,
            scheduled.creator_id,
            scheduled.name,
            scheduled.description,
            scheduled.start_time,
            scheduled.end_time,
        )
        if event is not None:
            await eventsync.sync_event(self, event.pk)  # publie le message d'inscription

    async def on_scheduled_event_update(
        self, before: discord.ScheduledEvent, after: discord.ScheduledEvent
    ) -> None:
        if not self._ours(after):
            return
        if after.status == discord.EventStatus.cancelled:
            event = await db(services.cancel_event_from_discord)(after.id)
        elif after.status == discord.EventStatus.scheduled:
            event = await db(services.update_event_from_discord)(
                after.id, after.name, after.description, after.start_time, after.end_time
            )
        else:
            return  # démarré / terminé côté Discord : rien à refléter
        if event is not None:
            await eventsync.sync_event(self, event.pk)

    async def on_scheduled_event_delete(self, scheduled: discord.ScheduledEvent) -> None:
        if not self._ours(scheduled):
            return
        event = await db(services.cancel_event_from_discord)(scheduled.id)
        if event is not None:
            await eventsync.sync_event(self, event.pk)


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
    token = discord_config().bot_token
    if not token:
        raise RuntimeError(
            "Token du bot manquant : à renseigner dans Guilde › Paramètres ou DISCORD_BOT_TOKEN."
        )
    GuildBot().run(token, log_handler=None)
