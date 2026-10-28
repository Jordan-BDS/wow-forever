from django.contrib import admin

from .models import (
    CharacterSnapshot,
    CompanionDevice,
    IgnoredCharacter,
    ImportBatch,
    PairingCode,
    WeeklyTitle,
)


@admin.register(PairingCode)
class PairingCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "user", "created_at", "expires_at", "used_at"]


@admin.register(CompanionDevice)
class CompanionDeviceAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "token_prefix", "created_at", "last_seen_at", "revoked_at"]
    readonly_fields = ["token_hash"]


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ["received_at", "user", "source", "addon_version", "summary"]
    list_filter = ["source"]
    readonly_fields = ["code", "fingerprint"]


@admin.register(CharacterSnapshot)
class CharacterSnapshotAdmin(admin.ModelAdmin):
    list_display = ["exported_at", "full_name", "user", "character", "status", "note"]
    list_filter = ["status"]
    search_fields = ["name", "guid"]


@admin.register(IgnoredCharacter)
class IgnoredCharacterAdmin(admin.ModelAdmin):
    list_display = ["name", "guid", "user", "created_at"]


@admin.register(WeeklyTitle)
class WeeklyTitleAdmin(admin.ModelAdmin):
    list_display = ["week_start", "label", "user", "character", "value"]
