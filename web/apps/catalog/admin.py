from django.contrib import admin

from .models import Article, DigestClickToken, DigestLog, Source, UserAffinity, UserRanking, YoutubeVideo


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


@admin.register(Source)
class SourceAdmin(ReadOnlyAdmin):
    list_display = ("name", "key", "category", "adapter_type", "is_active", "last_success_at")
    list_filter = ("category", "adapter_type", "is_active")
    search_fields = ("name", "key")


@admin.register(UserRanking)
class UserRankingAdmin(ReadOnlyAdmin):
    list_display = ("user", "content_type", "content_id", "rank", "relevance_score", "computed_at")
    list_filter = ("content_type",)
    search_fields = ("user__email",)
    ordering = ("user", "rank")


@admin.register(DigestLog)
class DigestLogAdmin(ReadOnlyAdmin):
    list_display = ("user", "sent_at")
    search_fields = ("user__email",)
    date_hierarchy = "sent_at"


@admin.register(UserAffinity)
class UserAffinityAdmin(ReadOnlyAdmin):
    list_display = ("user", "dimension", "key", "weight", "updated_at")
    list_filter = ("dimension",)
    search_fields = ("user__email", "key")
    ordering = ("-weight",)


@admin.register(DigestClickToken)
class DigestClickTokenAdmin(ReadOnlyAdmin):
    list_display = ("token", "user", "content_type", "content_id", "created_at")
    list_filter = ("content_type",)
    search_fields = ("user__email", "token")
    date_hierarchy = "created_at"
