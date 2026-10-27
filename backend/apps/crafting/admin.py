from django.contrib import admin

from .models import CraftRequest


@admin.register(CraftRequest)
class CraftRequestAdmin(admin.ModelAdmin):
    list_display = ["recipe", "quantity", "requester", "status", "crafter", "created_at"]
    list_filter = ["status", "recipe__profession"]
    search_fields = ["recipe__name", "requester__display_name"]
    autocomplete_fields = ["requester", "target_character", "crafter"]
