from rest_framework import serializers

from .models import Availability, SiteRole, User


class MemberSerializer(serializers.ModelSerializer):
    avatar_url = serializers.CharField(read_only=True)

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
        ]
        read_only_fields = fields


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["display_name", "bio"]
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
