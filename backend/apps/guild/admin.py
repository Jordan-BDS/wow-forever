from django.contrib import admin

from .models import GuildSettings


@admin.register(GuildSettings)
class GuildSettingsAdmin(admin.ModelAdmin):
    list_display = ["name", "faction", "realm", "updated_at"]

    def has_add_permission(self, request) -> bool:
        return not GuildSettings.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
