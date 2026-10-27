from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["display_name"]
    list_display = ["display_name", "discord_username", "discord_id", "site_role", "is_active", "last_login"]
    list_filter = ["site_role", "is_active"]
    search_fields = ["display_name", "discord_username", "discord_id"]
    readonly_fields = ["discord_id", "discord_username", "discord_avatar", "date_joined", "last_login"]
    fieldsets = (
        (None, {"fields": ("discord_id", "discord_username", "discord_avatar")}),
        ("Profil", {"fields": ("display_name", "bio")}),
        ("Accès", {"fields": ("site_role", "is_active", "deactivation_reason", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("date_joined", "last_login")}),
    )
    add_fieldsets = ((None, {"fields": ("discord_id", "display_name", "site_role")}),)
    filter_horizontal = ()
