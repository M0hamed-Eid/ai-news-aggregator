from django.contrib import admin

from .models import SavedItem, UserEvent


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "content_type", "content_id", "value", "created_at")
    list_filter = ("event_type", "content_type")
    search_fields = ("user__email",)
    date_hierarchy = "created_at"


@admin.register(SavedItem)
class SavedItemAdmin(admin.ModelAdmin):
    list_display = ("user", "content_type", "content_id", "is_saved", "is_read", "is_hidden", "updated_at")
    list_filter = ("is_saved", "is_read", "is_hidden", "content_type")
    search_fields = ("user__email",)
