from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsGM

from .models import GuildSettings


class GuildSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuildSettings
        fields = ["name", "faction", "realm", "discord_channel_id", "updated_at"]
        read_only_fields = ["updated_at"]


class GuildSettingsView(APIView):
    """Paramètres de la guilde : lecture pour tous les membres, modification par le GM."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [IsGM()]

    @extend_schema(responses=GuildSettingsSerializer)
    def get(self, request: Request) -> Response:
        return Response(GuildSettingsSerializer(GuildSettings.load()).data)

    @extend_schema(request=GuildSettingsSerializer, responses=GuildSettingsSerializer)
    def patch(self, request: Request) -> Response:
        serializer = GuildSettingsSerializer(GuildSettings.load(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
