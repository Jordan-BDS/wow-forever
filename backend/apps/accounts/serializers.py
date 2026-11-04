from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.notifications.models import DM_PREFERENCE_KINDS

from .models import Availability, SiteRole, User


class MemberSerializer(serializers.ModelSerializer):
    avatar_url = serializers.CharField(read_only=True)
    companion = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "discord_id",
            "discord_username",
            "display_name",
            "avatar_url",
            "bio",
            "site_role",
            "is_active",
            "deactivation_reason",
            "date_joined",
            "last_login",
            "dm_enabled",
            "dm_muted_kinds",
            "companion",
        ]
        read_only_fields = fields

    dm_muted_kinds = serializers.ListField(child=serializers.CharField(), read_only=True)

    @extend_schema_field(
        {
            "type": "object",
            "nullable": True,
            "properties": {
                "devices": {"type": "integer"},
                "last_seen_at": {"type": "string", "format": "date-time", "nullable": True},
            },
            "required": ["devices", "last_seen_at"],
        }
    )
    def get_companion(self, user: User) -> dict | None:
        """Compagnon lié : nombre de machines actives et dernier passage. Annoté par la liste des membres ;
        calculé à la demande ailleurs (fiche, /me)."""
        linked = getattr(user, "companion_linked", None)
        seen = getattr(user, "companion_seen_at", None)
        if linked is None:
            devices = user.companions.filter(revoked_at__isnull=True)
            linked = devices.count()
            seen = max((d.last_seen_at for d in devices if d.last_seen_at), default=None)
        if not linked:
            return None
        return {"devices": linked, "last_seen_at": seen.isoformat() if seen else None}


class MeUpdateSerializer(serializers.ModelSerializer):
    dm_muted_kinds = serializers.ListField(
        child=serializers.ChoiceField(choices=list(DM_PREFERENCE_KINDS)), required=False
    )

    class Meta:
        model = User
        fields = ["display_name", "bio", "dm_enabled", "dm_muted_kinds"]
        extra_kwargs = {"display_name": {"min_length": 2}}


class SetRoleSerializer(serializers.Serializer):
    site_role = serializers.ChoiceField(choices=SiteRole.choices)


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Availability
        fields = ["weekday", "start_hour", "end_hour"]
        extra_kwargs = {
            "start_hour": {"min_value": 0, "max_value": 23},
            "end_hour": {"min_value": 1, "max_value": 24},
        }

    def validate(self, attrs):
        if attrs["start_hour"] >= attrs["end_hour"]:
            raise serializers.ValidationError("L'heure de fin doit être après l'heure de début.")
        return attrs


class GuildAvailabilitySerializer(AvailabilitySlotSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    display_name = serializers.CharField(source="user.display_name", read_only=True)

    class Meta(AvailabilitySlotSerializer.Meta):
        fields = ["user", "display_name", *AvailabilitySlotSerializer.Meta.fields]
