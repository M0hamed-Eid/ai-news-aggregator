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
