from django.contrib import admin

from .models import Character, CharacterProfession


class CharacterProfessionInline(admin.TabularInline):
    model = CharacterProfession
    extra = 0


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "player_class", "race", "level", "main_role", "is_main"]
    list_filter = ["player_class", "main_role", "is_main"]
    search_fields = ["name", "owner__display_name"]
    autocomplete_fields = ["owner"]
    inlines = [CharacterProfessionInline]
