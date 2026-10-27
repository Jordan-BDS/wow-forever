from django.contrib import admin

from .models import Poll, Proposal, Vote


class ProposalInline(admin.TabularInline):
    model = Proposal
    extra = 0
    readonly_fields = ["author", "created_at"]


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "proposals_end", "votes_end", "sets_guild_name", "validated_proposal"]
    readonly_fields = ["validated_at", "validated_by", "created_by", "created_at"]
    inlines = [ProposalInline]


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ["proposal", "user", "created_at"]
