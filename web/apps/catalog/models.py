"""
Read-only Django models mapped onto tables OWNED BY THE PIPELINE.

These models are `managed = False`: Django never issues CREATE/ALTER/DROP for
them. Combined with PipelineRouter.allow_migrate() returning False and the
ReadOnly mixin below blocking save()/delete(), Django can ONLY read these tables.

The column definitions mirror the SQLAlchemy models in
app/database/models/{article,youtube_video,source,user_ranking}.py. If the
pipeline changes a column, update it here too (and see the schema-contract
test in the roadmap).
"""
from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class ReadOnly:
    """Mixin that turns any model into a hard read-only model at the ORM level."""

    _readonly_msg = "This record is owned by the pipeline and is read-only in Django."

    def save(self, *args, **kwargs):
        raise NotImplementedError(self._readonly_msg)

    def delete(self, *args, **kwargs):
        raise NotImplementedError(self._readonly_msg)


class Article(ReadOnly, models.Model):
    """Blog/news article scraped by the pipeline (table: articles)."""

    SOURCE_LABELS = {
        "blog_openai": "OpenAI",
        "blog_anthropic": "Anthropic",
        "arxiv": "arXiv",
        "github_release": "GitHub Releases",
        "reddit": "Reddit",
        "government_us": "US Federal Register",
        "government_uk": "UK Government",
        "government_nist": "NIST",
        "funding_crunchbase": "Crunchbase News",
        "huggingface_model": "Hugging Face",
    }

    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=500)
    url = models.CharField(max_length=2048, unique=True)
    source = models.CharField(max_length=50)
    author = models.CharField(max_length=200)
    content = models.TextField()
    summary = models.TextField(null=True, blank=True)
    tags = models.CharField(max_length=1000, null=True, blank=True)
    image_url = models.CharField(max_length=2048, null=True, blank=True)
    published_at = models.DateTimeField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "articles"
        ordering = ["-published_at"]
        verbose_name = "article"
        verbose_name_plural = "articles"

    def __str__(self):
        return self.title

    @property
    def source_label(self):
        return self.SOURCE_LABELS.get(self.source, self.source)

    @property
    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]


class YoutubeVideo(ReadOnly, models.Model):
    """YouTube video + transcript scraped by the pipeline (table: youtube_videos)."""

    id = models.BigAutoField(primary_key=True)
    video_id = models.CharField(max_length=20, unique=True)
    channel_name = models.CharField(max_length=200)
    channel_id = models.CharField(max_length=50, null=True, blank=True)
    title = models.CharField(max_length=500)
    url = models.CharField(max_length=2048, unique=True)
    source = models.CharField(max_length=20, default="youtube")
    content = models.TextField(null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    tags = models.CharField(max_length=1000, null=True, blank=True)
    transcript_segments = models.JSONField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    published_at = models.DateTimeField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "youtube_videos"
        ordering = ["-published_at"]
        verbose_name = "YouTube video"
        verbose_name_plural = "YouTube videos"

    def __str__(self):
        return self.title

    @property
    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def watch_url(self):
        return self.url or f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def embed_url(self):
        return f"https://www.youtube.com/embed/{self.video_id}"

    @property
    def thumbnail_url(self):
        return f"https://i.ytimg.com/vi/{self.video_id}/hqdefault.jpg"


class Source(ReadOnly, models.Model):
    """A configured ingestion source from the pipeline's Source Registry (table: sources)."""

    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50)
    adapter_type = models.CharField(max_length=20)
    handler = models.CharField(max_length=50, null=True, blank=True)
    config = models.JSONField(default=dict)
    schedule_hours = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    # User-submitted sources (M10) — created_by is a plain int (Django's own
    # users.id), not a FK, since this table is pipeline-owned and doesn't
    # know about Django's user table at the SQLAlchemy-model level either.
    created_by = models.BigIntegerField(null=True, blank=True)
    visibility = models.CharField(max_length=20, default="global")
    feed_url = models.CharField(max_length=2048, null=True, blank=True)
    validation_status = models.CharField(max_length=20, null=True, blank=True)
    validation_score = models.FloatField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    CATEGORY_LABELS = {
        "research": "Research",
        "open_source": "Open Source",
        "product_model_databases": "Product / Model Databases",
        "developer_communities": "Developer Communities",
        "government": "Government",
        "funding": "Funding",
        "media": "Media",
    }

    class Meta:
        managed = False
        db_table = "sources"
        ordering = ["category", "name"]
        verbose_name = "source"
        verbose_name_plural = "sources"

    def __str__(self):
        return self.name

    @property
    def category_label(self):
        return self.CATEGORY_LABELS.get(self.category, self.category)


class UserRanking(ReadOnly, models.Model):
    """
    Persisted output of CuratorAgent's ranking pass for one user (table:
    user_rankings) — written by app/services/digest_service.py, read-only
    here. `user` uses db_constraint=False: the FK is for Django ORM
    ergonomics only (request.user.rankings.all()) since this table is
    SQLAlchemy-owned and Django must never attempt to enforce or migrate it.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="user_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="rankings",
    )
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    rank = models.IntegerField()
    relevance_score = models.FloatField()
    reasoning = models.TextField(blank=True, default="")
    score_version = models.CharField(max_length=50, blank=True, default="")
    features = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "user_rankings"
        ordering = ["rank"]
        verbose_name = "user ranking"
        verbose_name_plural = "user rankings"

    def __str__(self):
        return f"rank {self.rank} — {self.content_type}:{self.content_id} (user_id={self.user_id})"

    @property
    def content_object(self):
        """Resolve to the actual Article or YoutubeVideo this ranking points at, or None."""
        if self.content_type == "article":
            return Article.objects.filter(pk=self.content_id).first()
        if self.content_type == "youtube_video":
            return YoutubeVideo.objects.filter(pk=self.content_id).first()
        return None


class UserAffinity(ReadOnly, models.Model):
    """
    Per-user affinity weight derived from behavioral events (table:
    user_affinities) — written by the nightly aggregation Celery task
    (app/tasks/affinity_tasks.py), read-only here. Only dimension='source'
    produces real rows until M8 ships topic/entity taxonomy.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="user_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="affinities",
    )
    dimension = models.CharField(max_length=20)
    key = models.CharField(max_length=200)
    weight = models.FloatField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "user_affinities"
        ordering = ["-weight"]
        verbose_name = "user affinity"
        verbose_name_plural = "user affinities"

    def __str__(self):
        return f"user_id={self.user_id} {self.dimension}={self.key} weight={self.weight:.3f}"


class DigestClickToken(ReadOnly, models.Model):
    """
    One row per (recipient, item) minted when a digest email is built (table:
    digest_click_tokens) — written by app/services/digest_service.py,
    read-only here. Looked up by apps.behavior's DigestRedirectView to
    attribute a digest click to a user + item before redirecting to the real
    content URL.
    """

    id = models.BigAutoField(primary_key=True)
    token = models.CharField(max_length=32, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="user_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="digest_click_tokens",
    )
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "digest_click_tokens"
        verbose_name = "digest click token"
        verbose_name_plural = "digest click tokens"

    def __str__(self):
        return f"token={self.token} user_id={self.user_id} {self.content_type}:{self.content_id}"

    @property
    def content_object(self):
        """Resolve to the actual Article or YoutubeVideo this token points at, or None."""
        if self.content_type == "article":
            return Article.objects.filter(pk=self.content_id).first()
        if self.content_type == "youtube_video":
            return YoutubeVideo.objects.filter(pk=self.content_id).first()
        return None


class DigestLog(ReadOnly, models.Model):
    """
    One row per digest email actually sent (table: digest_log) — written by
    run_pipeline.py's run_digest_phase after a successful send. Exists so the
    profile page can show "digests received: N" without the pipeline ever
    writing into a Django-owned table (see module docstring on why writes
    only ever go one direction per ORM).
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="user_id",
        db_constraint=False,
        on_delete=models.DO_NOTHING,
        related_name="digest_log_entries",
    )
    sent_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "digest_log"
        ordering = ["-sent_at"]
        verbose_name = "digest log entry"
        verbose_name_plural = "digest log entries"

    def __str__(self):
        return f"Digest sent to user_id={self.user_id} at {self.sent_at}"


# =============================================================================
# M8 — Content Intelligence Layer mirrors (app/database/models/{taxonomy_topic,
# content_topic,entity,content_entity,content_cluster,content_cluster_member,
# content_enrichment,content_score}.py). Same managed=False + ReadOnly pattern.
# =============================================================================

class TaxonomyTopic(ReadOnly, models.Model):
    """Controlled topic vocabulary (table: taxonomy_topics). Django's own
    onboarding.Interest FKs to this (by slug match) so user interests and
    content topics share ONE vocabulary — see Interest.taxonomy_topic."""

    id = models.BigAutoField(primary_key=True)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "taxonomy_topics"
        ordering = ["sort_order", "name"]
        verbose_name = "taxonomy topic"
        verbose_name_plural = "taxonomy topics"

    def __str__(self):
        return self.name


class ContentTopic(ReadOnly, models.Model):
    """Which taxonomy_topics a content item was tagged with (table: content_topics)."""

    id = models.BigAutoField(primary_key=True)
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    taxonomy_topic = models.ForeignKey(
        TaxonomyTopic, db_constraint=False, on_delete=models.DO_NOTHING, related_name="content_topics",
    )
    confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "content_topics"
        verbose_name = "content topic"
        verbose_name_plural = "content topics"

    def __str__(self):
        return f"{self.content_type}:{self.content_id} -> {self.taxonomy_topic_id}"


class Entity(ReadOnly, models.Model):
    """Deduplicated named entity — company/model/person/technology (table: entities)."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=200)
    entity_type = models.CharField(max_length=20)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "entities"
        verbose_name = "entity"
        verbose_name_plural = "entities"

    def __str__(self):
        return f"{self.name} ({self.entity_type})"


class ContentEntity(ReadOnly, models.Model):
    """Which entities were mentioned in a content item (table: content_entities)."""

    id = models.BigAutoField(primary_key=True)
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    entity = models.ForeignKey(
        Entity, db_constraint=False, on_delete=models.DO_NOTHING, related_name="content_mentions",
    )
    mention_context = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "content_entities"
        verbose_name = "content entity"
        verbose_name_plural = "content entities"

    def __str__(self):
        return f"{self.content_type}:{self.content_id} -> {self.entity_id}"


class ContentCluster(ReadOnly, models.Model):
    """A cluster identity/bucket — actual grouping lives in ContentClusterMember (table: content_clusters)."""

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "content_clusters"
        verbose_name = "content cluster"
        verbose_name_plural = "content clusters"

    def __str__(self):
        return f"Cluster {self.id}"


class ContentClusterMember(ReadOnly, models.Model):
    """One item's membership in a cluster (table: content_cluster_members)."""

    id = models.BigAutoField(primary_key=True)
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    cluster = models.ForeignKey(
        ContentCluster, db_constraint=False, on_delete=models.DO_NOTHING, related_name="members",
    )
    similarity_to_centroid = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "content_cluster_members"
        verbose_name = "content cluster member"
        verbose_name_plural = "content cluster members"

    def __str__(self):
        return f"{self.content_type}:{self.content_id} in cluster {self.cluster_id}"


class ContentEnrichment(ReadOnly, models.Model):
    """Structured enrichment output from EnrichmentAgent's single LLM call
    per item (table: content_enrichment) — content_category, technical_depth,
    structured summary fields, why_it_matters."""

    id = models.BigAutoField(primary_key=True)
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    content_category = models.CharField(max_length=30)
    technical_depth = models.IntegerField()
    key_points = models.JSONField(default=list)
    technical_details = models.TextField(blank=True, default="")
    business_angle = models.TextField(blank=True, default="")
    why_it_matters = models.TextField(blank=True, default="")
    enrichment_version = models.CharField(max_length=50)
    enriched_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "content_enrichment"
        verbose_name = "content enrichment"
        verbose_name_plural = "content enrichment"

    def __str__(self):
        return f"{self.content_type}:{self.content_id} category={self.content_category}"


class ContentScore(ReadOnly, models.Model):
    """Quality score v1 + logged feature-vector snapshot (table: content_scores)."""

    id = models.BigAutoField(primary_key=True)
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    score = models.FloatField()
    score_version = models.CharField(max_length=50)
    features = models.JSONField(default=dict)
    computed_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "content_scores"
        ordering = ["-score"]
        verbose_name = "content score"
        verbose_name_plural = "content scores"

    def __str__(self):
        return f"{self.content_type}:{self.content_id} score={self.score:.3f}"


class Embedding(ReadOnly, models.Model):
    """
    pgvector embedding for one article/video (table: embeddings) — written by
    app/embeddings/embedding_service.py, read-only here. Added in M9 so
    semantic search (web/apps/news/search.py) can run a cosine-distance query
    directly against the shared Postgres instance via Django's own connection
    — no ML dependency needed in this process, only pgvector's lightweight
    (pure Python + numpy) Django integration. Turning a user's free-text
    query into a vector still requires the actual embedding MODEL, which
    Django does not load; that happens via a dedicated Celery task on its own
    queue (app/tasks/search_tasks.py) — see that module's docstring.
    """

    id = models.BigAutoField(primary_key=True)
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    embedding = VectorField(dimensions=384)
    model_name = models.CharField(max_length=100)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "embeddings"
        verbose_name = "embedding"
        verbose_name_plural = "embeddings"

    def __str__(self):
        return f"{self.content_type}:{self.content_id}"


class PersonEntity(ReadOnly, models.Model):
    """
    Links a person Entity to their own scrapeable footprint (table:
    person_entities, M10) — written by the pipeline once a footprint is
    registered/validated, read-only here. `source` resolves to the actual
    Source Registry row being scraped for this footprint (null until
    registered).
    """

    id = models.BigAutoField(primary_key=True)
    entity = models.ForeignKey(
        Entity, db_constraint=False, on_delete=models.DO_NOTHING, related_name="footprints",
    )
    footprint_type = models.CharField(max_length=20)
    source = models.ForeignKey(
        "Source", db_constraint=False, on_delete=models.DO_NOTHING, null=True, blank=True,
        related_name="person_footprint",
    )
    external_identifier = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "person_entities"
        verbose_name = "person entity"
        verbose_name_plural = "person entities"

    def __str__(self):
        return f"{self.entity.name} ({self.footprint_type})"


class Trend(ReadOnly, models.Model):
    """
    Daily burst-detection row (table: trends, M11) — one per (dimension, key,
    date). Written by run_pipeline.py's run_trend_computation_phase(); this
    same table serves both the Home Trending module (today's is_trending=True
    rows) and an entity page's mention timeline (filter dimension='entity',
    key=str(entity_id)) — deliberately the only table for this, see the
    SQLAlchemy model's own docstring for why a second "materialized" table
    would be redundant.
    """

    id = models.BigAutoField(primary_key=True)
    dimension = models.CharField(max_length=20)
    key = models.CharField(max_length=200)
    date = models.DateField()
    mention_count = models.IntegerField()
    baseline_mean = models.FloatField()
    baseline_stddev = models.FloatField()
    z_score = models.FloatField(null=True, blank=True)
    is_trending = models.BooleanField()
    computed_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "trends"
        ordering = ["-date", "-z_score"]
        verbose_name = "trend"
        verbose_name_plural = "trends"

    def __str__(self):
        return f"{self.dimension}:{self.key} {self.date} (z={self.z_score})"


class TrendReport(ReadOnly, models.Model):
    """Weekly grounded trend narrative (table: trend_reports, M11, Pro) — see the SQLAlchemy model's own docstring for the citation-grounding design."""

    id = models.BigAutoField(primary_key=True)
    week_start_date = models.DateField()
    narrative = models.JSONField()
    raw_narrative = models.JSONField(null=True, blank=True)
    narrative_version = models.CharField(max_length=50)
    llm_model = models.CharField(max_length=100)
    generated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "trend_reports"
        ordering = ["-week_start_date"]
        verbose_name = "trend report"
        verbose_name_plural = "trend reports"

    def __str__(self):
        return f"Trend report for week of {self.week_start_date}"


class ContentChunk(ReadOnly, models.Model):
    """Chunk-level chaptered summary (table: content_chunks, M12) — one row per ~10-minute chunk of a long video. See the SQLAlchemy model's own docstring for the map-reduce design."""

    id = models.BigAutoField(primary_key=True)
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    chunk_index = models.IntegerField()
    start_seconds = models.FloatField()
    end_seconds = models.FloatField()
    chapter_title = models.CharField(max_length=200)
    chunk_summary = models.TextField()
    summary_version = models.CharField(max_length=50)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "content_chunks"
        ordering = ["content_type", "content_id", "chunk_index"]
        verbose_name = "content chunk"
        verbose_name_plural = "content chunks"

    def __str__(self):
        return f"{self.content_type}:{self.content_id} chunk #{self.chunk_index}"


class SttJob(ReadOnly, models.Model):
    """STT job status/metadata (table: stt_jobs, M12) — one row per video; also the single source of truth for how ANY video got its transcript (manual_caption/auto_caption/stt)."""

    id = models.BigAutoField(primary_key=True)
    content_type = models.CharField(max_length=20)
    content_id = models.BigIntegerField()
    status = models.CharField(max_length=20)
    transcript_source = models.CharField(max_length=20, null=True, blank=True)
    whisper_model = models.CharField(max_length=50, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    requested_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "stt_jobs"
        verbose_name = "STT job"
        verbose_name_plural = "STT jobs"

    def __str__(self):
        return f"{self.content_type}:{self.content_id} — {self.status}"
