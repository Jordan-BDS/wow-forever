"""
Côté Discord de la synchronisation des événements : l'événement planifié de l'onglet « Événements »
et le message d'inscription à boutons dans le salon des annonces.

Le bot appelle `sync_event` à chaque demande `event_sync` dépilée de l'outbox, après un clic sur un bouton,
et après chaque changement reçu de Discord. La logique métier (ORM) reste dans `services`.
"""

import logging
import re

import discord
from asgiref.sync import sync_to_async
from django.utils import timezone

from . import services

logger = logging.getLogger(__name__)

db = sync_to_async

BUTTONS = [
    ("present", "Présent", discord.ButtonStyle.success, "✅"),
    ("maybe", "Peut-être", discord.ButtonStyle.secondary, "🤔"),
    ("late", "En retard", discord.ButtonStyle.secondary, "⏰"),
    ("absent", "Absent", discord.ButtonStyle.secondary, "🚫"),
    ("leave", "Me désinscrire", discord.ButtonStyle.danger, None),
]


class SignupButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"evt:(?P<event>\d+):(?P<status>present|maybe|late|absent|leave)",
):
    """Bouton persistant : son custom_id porte l'événement et le statut, il survit aux redémarrages du bot."""

    def __init__(self, event_id: int, status: str) -> None:
        _, label, style, emoji = next(b for b in BUTTONS if b[0] == status)
        super().__init__(
            discord.ui.Button(label=label, style=style, emoji=emoji, custom_id=f"evt:{event_id}:{status}")
        )
        self.event_id = event_id
        self.status = status

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match, /
    ):
        return cls(int(match["event"]), match["status"])

    async def callback(self, interaction: discord.Interaction) -> None:
        message, choices = await db(services.quick_signup)(
            str(interaction.user.id), self.event_id, self.status
        )
        if choices:
            view = ChoiceView(self.event_id, self.status, choices)
            await interaction.response.send_message(message, view=view, ephemeral=True)
            return
        await interaction.response.send_message(message, ephemeral=True)
        await sync_event(interaction.client, self.event_id)


class ChoiceView(discord.ui.View):
    """Menu éphémère « perso — rôle » quand le joueur a plusieurs possibilités."""

    def __init__(self, event_id: int, status: str, choices: list[tuple[str, str]]) -> None:
        super().__init__(timeout=180)
        self.event_id = event_id
        self.status = status
        select = discord.ui.Select(
            placeholder="Personnage et rôle",
            options=[discord.SelectOption(label=label, value=value) for label, value in choices],
        )
        select.callback = self.chosen
        self.add_item(select)
        self.select = select

    async def chosen(self, interaction: discord.Interaction) -> None:
        message = await db(services.signup_with_choice)(
            str(interaction.user.id), self.event_id, self.status, self.select.values[0]
        )
        await interaction.response.edit_message(content=message, view=None)
        await sync_event(interaction.client, self.event_id)


def signup_view(event_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for status, *_ in BUTTONS:
        view.add_item(SignupButton(event_id, status))
    return view


# --- synchronisation ------------------------------------------------------------------------


async def sync_event(bot: discord.Client, event_id: int) -> None:
    """Aligne Discord sur l'état du site pour cet événement, puis acquitte les demandes en attente."""
    snapshot = await db(services.event_snapshot)(event_id)
    if snapshot is None:
        await db(services.complete_event_syncs)(event_id)
        return
    guild_id = bot.guild_object.id
    guild = bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
    try:
        await _sync_scheduled_event(guild, snapshot)
    except discord.Forbidden:
        logger.warning("Le bot n'a pas la permission « Gérer les événements » sur le serveur.")
    await _sync_signup_message(bot, snapshot)
    await db(services.complete_event_syncs)(event_id)


async def _fetch_scheduled(guild: discord.Guild, raw_id: str) -> discord.ScheduledEvent | None:
    if not raw_id.isdigit():
        return None
    try:
        return guild.get_scheduled_event(int(raw_id)) or await guild.fetch_scheduled_event(int(raw_id))
    except discord.NotFound:
        return None


async def _sync_scheduled_event(guild: discord.Guild, snap: services.EventSnapshot) -> None:
    existing = await _fetch_scheduled(guild, snap.discord_event_id)

    if not snap.planned:
        # Annulé (ou terminé) sur le site : on retire l'événement de l'onglet Discord, l'identifiant est
        # effacé avant la suppression pour que l'écho « scheduled_event_delete » ne retrouve rien à annuler.
        if existing is not None and existing.status in (
            discord.EventStatus.scheduled,
            discord.EventStatus.active,
        ):
            await db(services.store_discord_ids)(snap.id, discord_event_id="")
            await existing.delete(reason="Annulé sur le site")
        return

    if snap.starts_at <= timezone.now():
        return  # Discord refuse un événement planifié dans le passé

    if existing is None or existing.status not in (discord.EventStatus.scheduled, discord.EventStatus.active):
        created = await guild.create_scheduled_event(
            name=snap.name,
            start_time=snap.starts_at,
            end_time=snap.ends_at,
            description=snap.description,
            location=snap.location or "WoW Forever",
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            reason="Créé sur le site de la guilde",
        )
        await db(services.store_discord_ids)(snap.id, discord_event_id=str(created.id))
        return

    changes = {}
    if existing.name != snap.name:
        changes["name"] = snap.name
    if (existing.description or "") != snap.description:
        changes["description"] = snap.description
    if int(existing.start_time.timestamp()) != int(snap.starts_at.timestamp()):
        changes["start_time"] = snap.starts_at
    if existing.end_time is None or int(existing.end_time.timestamp()) != int(snap.ends_at.timestamp()):
        changes["end_time"] = snap.ends_at
    if snap.location and existing.location != snap.location:
        changes["location"] = snap.location
    if changes:
        await existing.edit(**changes, reason="Modifié sur le site")


async def _sync_signup_message(bot: discord.Client, snap: services.EventSnapshot) -> None:
    channel_id = await db(services.channel_id_for)("event_sync")
    if channel_id is None:
        return
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    view = signup_view(snap.id) if snap.planned and snap.signups_open else None

    message = None
    if snap.discord_message_id.isdigit():
        try:
            message = await channel.fetch_message(int(snap.discord_message_id))
        except discord.NotFound:
            message = None
    if message is None:
        if not snap.planned:
            return  # pas de message à poster pour un événement déjà annulé ou terminé
        message = await channel.send(snap.message_text, view=view)
        await db(services.store_discord_ids)(snap.id, discord_message_id=str(message.id))
    elif message.content != snap.message_text or bool(message.components) != bool(view):
        await message.edit(content=snap.message_text, view=view)


# --- sondages (message en lecture seule, réédité à chaque changement) ----------------------------


async def sync_poll(bot: discord.Client, poll_id: int) -> None:
    snapshot = await db(services.poll_snapshot)(poll_id)
    if snapshot is None:
        await db(services.complete_poll_syncs)(poll_id)
        return
    channel_id = await db(services.channel_id_for)("poll_sync")
    if channel_id is None:
        await db(services.complete_poll_syncs)(poll_id)
        return
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    message = None
    if snapshot.discord_message_id.isdigit():
        try:
            message = await channel.fetch_message(int(snapshot.discord_message_id))
        except discord.NotFound:
            message = None
    if message is None:
        message = await channel.send(snapshot.message_text)
    elif message.content != snapshot.message_text:
        await message.edit(content=snapshot.message_text)
    await db(services.store_poll_message)(poll_id, str(message.id), snapshot.status)
    await db(services.complete_poll_syncs)(poll_id)
