from django.urls import path

from .views import GuildSettingsView

urlpatterns = [
    path("guild/", GuildSettingsView.as_view(), name="guild-settings"),
]
