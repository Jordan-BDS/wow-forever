from django.contrib import admin

from .models import BlizzardRecord


@admin.register(BlizzardRecord)
class BlizzardRecordAdmin(admin.ModelAdmin):
    list_display = ["fetched_at", "kind", "slug", "character", "http_status"]
    list_filter = ["kind", "http_status"]
    search_fields = ["slug"]
    readonly_fields = ["fetched_at", "kind", "slug", "character", "http_status", "data"]
