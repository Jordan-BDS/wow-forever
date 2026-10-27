from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "recipient", "status", "attempts", "sent_at"]
    list_filter = ["status", "kind"]
    search_fields = ["text", "recipient__display_name"]
    readonly_fields = ["created_at", "sent_at"]
    actions = ["requeue"]

    @admin.action(description="Remettre en attente")
    def requeue(self, request, queryset):
        queryset.update(status="pending", error="", attempts=0)
