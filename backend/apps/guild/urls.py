from django.urls import path

from .views import DiscordCheckView, GuildSettingsView

urlpatterns = [
    path("guild/", GuildSettingsView.as_view(), name="guild-settings"),
    path("guild/discord-check/", DiscordCheckView.as_view(), name="guild-discord-check"),
]
