"""
Read-only Django models mapped onto tables OWNED BY THE PIPELINE.

These models are `managed = False`: Django never issues CREATE/ALTER/DROP for
them. Combined with PipelineRouter.allow_migrate() returning False and the
ReadOnly mixin below blocking save()/delete(), Django can ONLY read these tables.

The column definitions mirror the SQLAlchemy models in
app/database/models/{article,youtube_video}.py. If the pipeline changes a
column, update it here too (and see the schema-contract test in the roadmap).
"""
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
    }

    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=500)
    url = models.CharField(max_length=2048, unique=True)
    source = models.CharField(max_length=50)
    author = models.CharField(max_length=200)
    content = models.TextField()
    summary = models.TextField(null=True, blank=True)
    tags = models.CharField(max_length=1000, null=True, blank=True)
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
