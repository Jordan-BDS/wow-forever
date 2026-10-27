from django.contrib import admin

from .models import Event, Signup


class SignupInline(admin.TabularInline):
    model = Signup
    extra = 0
    autocomplete_fields = ["user", "character"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "instance", "starts_at", "organizer", "status"]
    list_filter = ["kind", "status"]
    search_fields = ["title"]
    autocomplete_fields = ["organizer"]
    inlines = [SignupInline]
