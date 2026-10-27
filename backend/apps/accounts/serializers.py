from rest_framework import serializers

from .models import SiteRole, User


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
