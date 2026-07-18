from django.contrib import admin

from .models import (
    Article, ContentChunk, ContentCluster, ContentClusterMember, ContentEnrichment, ContentEntity,
    ContentScore, ContentTopic, DigestClickToken, DigestLog, Embedding, Entity,
    PersonEntity, Source, SttJob, TaxonomyTopic, Trend, TrendReport, UserAffinity, UserRanking, YoutubeVideo,
)


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


@admin.register(TaxonomyTopic)
class TaxonomyTopicAdmin(ReadOnlyAdmin):
    list_display = ("name", "slug", "category", "sort_order", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "slug")
    ordering = ("sort_order",)


@admin.register(ContentTopic)
class ContentTopicAdmin(ReadOnlyAdmin):
    list_display = ("content_type", "content_id", "taxonomy_topic", "confidence")
    list_filter = ("content_type", "taxonomy_topic")


@admin.register(Entity)
class EntityAdmin(ReadOnlyAdmin):
    list_display = ("name", "entity_type", "created_at")
    list_filter = ("entity_type",)
    search_fields = ("name",)


@admin.register(ContentEntity)
class ContentEntityAdmin(ReadOnlyAdmin):
    list_display = ("content_type", "content_id", "entity")
    list_filter = ("content_type",)


@admin.register(ContentCluster)
class ContentClusterAdmin(ReadOnlyAdmin):
    list_display = ("id", "created_at", "updated_at")


@admin.register(ContentClusterMember)
class ContentClusterMemberAdmin(ReadOnlyAdmin):
    list_display = ("content_type", "content_id", "cluster", "similarity_to_centroid")
    list_filter = ("content_type",)


@admin.register(ContentEnrichment)
class ContentEnrichmentAdmin(ReadOnlyAdmin):
    list_display = ("content_type", "content_id", "content_category", "technical_depth", "enrichment_version", "enriched_at")
    list_filter = ("content_category", "technical_depth", "enrichment_version")
    date_hierarchy = "enriched_at"


@admin.register(ContentScore)
class ContentScoreAdmin(ReadOnlyAdmin):
    list_display = ("content_type", "content_id", "score", "score_version", "computed_at")
    list_filter = ("score_version",)
    ordering = ("-score",)


@admin.register(Embedding)
class EmbeddingAdmin(ReadOnlyAdmin):
    list_display = ("content_type", "content_id", "model_name", "created_at")
    list_filter = ("content_type", "model_name")


@admin.register(PersonEntity)
class PersonEntityAdmin(ReadOnlyAdmin):
    list_display = ("entity", "footprint_type", "source", "external_identifier", "created_at")
    list_filter = ("footprint_type",)
    search_fields = ("entity__name", "external_identifier")


@admin.register(Trend)
class TrendAdmin(ReadOnlyAdmin):
    list_display = ("dimension", "key", "date", "mention_count", "z_score", "is_trending")
    list_filter = ("dimension", "is_trending")
    search_fields = ("key",)
    ordering = ("-date", "-z_score")


@admin.register(TrendReport)
class TrendReportAdmin(ReadOnlyAdmin):
    list_display = ("week_start_date", "narrative_version", "llm_model", "generated_at")
    ordering = ("-week_start_date",)


@admin.register(ContentChunk)
class ContentChunkAdmin(ReadOnlyAdmin):
    list_display = ("content_type", "content_id", "chunk_index", "chapter_title", "start_seconds", "end_seconds")
    list_filter = ("content_type",)
    ordering = ("content_type", "content_id", "chunk_index")


@admin.register(SttJob)
class SttJobAdmin(ReadOnlyAdmin):
    list_display = ("content_type", "content_id", "status", "transcript_source", "whisper_model", "requested_at")
    list_filter = ("status", "transcript_source")
