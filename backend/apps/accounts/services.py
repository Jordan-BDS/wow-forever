"""Opérations sur les comptes : connexion Discord, activation, désactivation."""

import logging

from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from apps.guild.config import discord_config

from . import discord
from .models import DeactivationReason, SiteRole, User

logger = logging.getLogger(__name__)


class AccessDenied(Exception):
    """L'utilisateur Discord n'a pas le droit d'accéder au site. `code` est renvoyé au front."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def has_allowed_role(member: dict | None) -> bool:
    if member is None:
        return False
    allowed = set(discord_config().allowed_role_ids)
    return bool(allowed & set(member.get("roles", [])))


def delete_user_sessions(user: User) -> int:
    """Supprime toutes les sessions ouvertes d'un utilisateur (coupe l'accès immédiatement)."""
    deleted = 0
    for session in Session.objects.iterator():
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            session.delete()
            deleted += 1
    return deleted


def deactivate_user(user: User, reason: str) -> None:
    user.is_active = False
    user.deactivation_reason = reason
    user.save(update_fields=["is_active", "deactivation_reason"])
    delete_user_sessions(user)
    logger.info("Compte %s désactivé (%s)", user.discord_id, reason)


def reactivate_user(user: User) -> None:
    user.is_active = True
    user.deactivation_reason = ""
    user.save(update_fields=["is_active", "deactivation_reason"])
    logger.info("Compte %s réactivé", user.discord_id)


@transaction.atomic
def login_from_discord(code: str) -> User:
    """
    Échange le code OAuth, vérifie l'appartenance au serveur et le rôle Discord,
    puis crée ou met à jour le compte. Lève AccessDenied si l'accès est refusé.
    """
    token = discord.exchange_code(code)
    me = discord.fetch_me(token["access_token"])
    member = discord.fetch_guild_member(me["id"])

    if member is None:
        raise AccessDenied("not_member")
    if not has_allowed_role(member):
        raise AccessDenied("missing_role")

    username = me.get("global_name") or me["username"]
    user, created = User.objects.get_or_create(
        discord_id=me["id"],
        defaults={"discord_username": username, "display_name": username},
    )
    user.discord_username = username
    user.discord_avatar = me.get("avatar") or ""
    if not user.display_name:
        user.display_name = username

    first_gm = discord_config().first_gm_id
    if first_gm and user.discord_id == first_gm:
        user.site_role = SiteRole.GM

    if not user.is_active:
        if user.deactivation_reason == DeactivationReason.MANUAL:
            user.save()
            raise AccessDenied("deactivated")
        # Rôle Discord rendu : on réactive.
        user.is_active = True
        user.deactivation_reason = ""

    user.last_login = timezone.now()
    user.save()
    logger.info("Connexion Discord de %s (%s)", user.discord_id, "création" if created else "mise à jour")
    return user
