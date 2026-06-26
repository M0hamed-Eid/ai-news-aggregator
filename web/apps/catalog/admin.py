from django.contrib import admin

from .models import Article, YoutubeVideo


class ReadOnlyAdmin(admin.ModelAdmin):
    """Lets staff browse pipeline content in the admin without any write access."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Article)
class ArticleAdmin(ReadOnlyAdmin):
    list_display = ("title", "source", "author", "published_at")
    list_filter = ("source",)
    search_fields = ("title", "author", "tags")
    date_hierarchy = "published_at"
    ordering = ("-published_at",)


@admin.register(YoutubeVideo)
class YoutubeVideoAdmin(ReadOnlyAdmin):
    list_display = ("title", "channel_name", "published_at")
    list_filter = ("channel_name",)
    search_fields = ("title", "channel_name", "tags")
    date_hierarchy = "published_at"
    ordering = ("-published_at",)
