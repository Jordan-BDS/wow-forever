from django.contrib import admin

from .models import PlayerClass, Profession, ProfessionSpecialization, Race, Specialization


class SpecializationInline(admin.TabularInline):
    model = Specialization
    extra = 0


@admin.register(PlayerClass)
class PlayerClassAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "color", "order"]
    inlines = [SpecializationInline]


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "faction", "order"]
    list_filter = ["faction"]
    filter_horizontal = ["classes"]


class ProfessionSpecializationInline(admin.TabularInline):
    model = ProfessionSpecialization
    extra = 0


@admin.register(Profession)
class ProfessionAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "kind", "order"]
    list_filter = ["kind"]
    inlines = [ProfessionSpecializationInline]
