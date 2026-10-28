import httpx
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsGM

from .config import discord_config
from .models import GuildSettings

PUBLIC_FIELDS = ["name", "faction", "realm", "values", "updated_at"]
ID_FIELDS = ("discord_guild_id", "discord_first_gm_id", "discord_client_id")
CHANNEL_FIELDS = (
    "discord_channel_id",
    "discord_agenda_channel_id",
    "discord_crafts_channel_id",
    "discord_polls_channel_id",
)


class GuildSettingsSerializer(serializers.ModelSerializer):
    """Réglages complets, réservés au GM. Les secrets ne sont jamais renvoyés, seulement « défini ou non »."""

    discord_client_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    discord_bot_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    discord_client_secret_set = serializers.SerializerMethodField()
    discord_bot_token_set = serializers.SerializerMethodField()
    discord_login_ready = serializers.SerializerMethodField()

    class Meta:
        model = GuildSettings
        fields = [
            *PUBLIC_FIELDS,
            "discord_channel_id",
            "discord_agenda_channel_id",
            "discord_crafts_channel_id",
            "discord_polls_channel_id",
            "reminder_minutes",
            "discord_client_id",
            "discord_client_secret",
            "discord_client_secret_set",
            "discord_bot_token",
            "discord_bot_token_set",
            "discord_guild_id",
            "discord_allowed_role_ids",
            "discord_first_gm_id",
            "discord_login_ready",
        ]
        read_only_fields = ["updated_at"]

    def get_discord_client_secret_set(self, obj: GuildSettings) -> bool:
        return bool(discord_config().client_secret)

    def get_discord_bot_token_set(self, obj: GuildSettings) -> bool:
        return bool(discord_config().bot_token)

    def get_discord_login_ready(self, obj: GuildSettings) -> bool:
        return discord_config().login_ready

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Valeurs effectives (site ou environnement) pour les champs non secrets.
        config = discord_config()
        data["discord_client_id"] = config.client_id
        data["discord_guild_id"] = config.guild_id
        data["discord_allowed_role_ids"] = ", ".join(config.allowed_role_ids)
        data["discord_first_gm_id"] = config.first_gm_id
        return data

    def validate(self, attrs):
        if "values" in attrs:
            attrs["values"] = attrs["values"].replace("\r\n", "\n").strip()
        for field in ("discord_client_secret", "discord_bot_token"):
            if field in attrs and attrs[field] == "":
                attrs.pop(field)  # champ laissé vide = on garde la valeur actuelle
        if "discord_allowed_role_ids" in attrs:
            ids = [
                r.strip() for r in attrs["discord_allowed_role_ids"].replace(";", ",").split(",") if r.strip()
            ]
            if any(not r.isdigit() for r in ids):
                raise serializers.ValidationError(
                    {"discord_allowed_role_ids": "Des IDs numériques séparés par des virgules."}
                )
            attrs["discord_allowed_role_ids"] = ",".join(ids)
        for field in (*ID_FIELDS, *CHANNEL_FIELDS):
            value = attrs.get(field)
            if value and not value.isdigit():
                raise serializers.ValidationError({field: "Un identifiant Discord est numérique."})
        return attrs


class PublicGuildSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuildSettings
        fields = PUBLIC_FIELDS


class GuildSettingsView(APIView):
    """Nom, faction et royaume pour tous les membres ; réglages complets et modification pour le GM."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [IsGM()]

    @extend_schema(responses=GuildSettingsSerializer)
    def get(self, request: Request) -> Response:
        instance = GuildSettings.load()
        if request.user.is_gm:
            return Response(GuildSettingsSerializer(instance).data)
        return Response(PublicGuildSettingsSerializer(instance).data)

    @extend_schema(request=GuildSettingsSerializer, responses=GuildSettingsSerializer)
    def patch(self, request: Request) -> Response:
        serializer = GuildSettingsSerializer(GuildSettings.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DiscordRoleSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    allowed = serializers.BooleanField()


class DiscordChannelSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField(allow_blank=True)


class DiscordCheckSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    detail = serializers.CharField()
    guild_name = serializers.CharField(allow_blank=True)
    roles = DiscordRoleSerializer(many=True)
    channels = DiscordChannelSerializer(many=True)


def _failure(detail: str) -> Response:
    return Response({"ok": False, "detail": detail, "guild_name": "", "roles": [], "channels": []})


def text_channels(channels: list[dict]) -> list[dict]:
    """Salons texte triés comme dans Discord (catégorie puis position), avec le nom de leur catégorie."""
    categories = {c["id"]: c for c in channels if c["type"] == 4}
    listing = [c for c in channels if c["type"] == 0]
    listing.sort(
        key=lambda c: (
            categories.get(c.get("parent_id") or "", {}).get("position", -1),
            c.get("position", 0),
        )
    )
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "category": categories.get(c.get("parent_id") or "", {}).get("name", ""),
        }
        for c in listing
    ]


class DiscordCheckView(APIView):
    """Vérifie, avec le token du bot, que le serveur est joignable ; liste ses rôles et ses salons texte."""

    permission_classes = [IsGM]

    @extend_schema(request=None, responses=DiscordCheckSerializer)
    def post(self, request: Request) -> Response:
        config = discord_config()
        if not config.bot_token or not config.guild_id:
            return _failure("Renseigne d'abord le token du bot et l'ID du serveur.")
        headers = {"Authorization": f"Bot {config.bot_token}"}
        try:
            guild = httpx.get(
                f"{settings.DISCORD_API_BASE}/guilds/{config.guild_id}", headers=headers, timeout=10.0
            )
            roles = httpx.get(
                f"{settings.DISCORD_API_BASE}/guilds/{config.guild_id}/roles", headers=headers, timeout=10.0
            )
            channels = httpx.get(
                f"{settings.DISCORD_API_BASE}/guilds/{config.guild_id}/channels",
                headers=headers,
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            return _failure(f"Discord injoignable : {exc}")
        if guild.status_code == 401:
            return _failure("Token du bot refusé par Discord.")
        if guild.status_code in (403, 404):
            return _failure("Le bot n'est pas sur ce serveur, ou l'ID du serveur est faux.")
        if guild.is_error or roles.is_error:
            return _failure(f"Discord a répondu {guild.status_code}.")
        allowed = set(config.allowed_role_ids)
        listing = [
            {"id": role["id"], "name": role["name"], "allowed": role["id"] in allowed}
            for role in sorted(roles.json(), key=lambda r: -r.get("position", 0))
            if role["name"] != "@everyone"
        ]
        missing = allowed - {r["id"] for r in listing}
        detail = f"Serveur « {guild.json().get('name', '')} » joignable."
        if missing:
            detail += f" Rôles autorisés introuvables : {', '.join(sorted(missing))}."
        elif not allowed:
            detail += " Aucun rôle autorisé : personne ne pourra se connecter."
        return Response(
            {
                "ok": not missing and bool(allowed),
                "detail": detail,
                "guild_name": guild.json().get("name", ""),
                "roles": listing,
                "channels": text_channels(channels.json()) if channels.is_success else [],
            }
        )
