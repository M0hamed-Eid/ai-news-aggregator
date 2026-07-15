"""
Behavioral instrumentation (M7): raw event capture (user_events) and
per-item save/read/hide state (saved_items).

UserEvent is APPEND-ONLY — every row is a fact about what happened, never
updated or deleted except by the nightly retention prune (see
management/commands/prune_old_events.py).

SavedItem is a per-(user, content) STATE table, upserted by whichever
interaction happens first — an explicit save, a page view marking something
read, or a hide action — not literally restricted to rows the user has
bookmarked. Its success criterion (per docs/ROADMAP.md M7) is explicit that
clicking/dwelling on an item, not just saving it, produces a saved_items row.
"""
from django.conf import settings
from django.db import models


CONTENT_TYPE_CHOICES = [
    ("article", "Article"),
    ("youtube_video", "YouTube video"),
]


class UserEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ("impression", "Impression"),
        ("click", "Click"),
        ("dwell", "Dwell"),
        ("scroll", "Scroll"),
        ("save", "Save"),
        ("hide", "Hide"),
        ("search", "Search"),
        ("digest_click", "Digest click"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, null=True, blank=True)
    content_id = models.BigIntegerField(null=True, blank=True)
    value = models.FloatField(
        null=True, blank=True,
        help_text="Numeric payload whose meaning depends on event_type — dwell ms, scroll %, etc.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_events"
        indexes = [models.Index(fields=["user", "created_at"], name="ix_user_events_user_created")]

    def __str__(self):
        return f"user_id={self.user_id} {self.event_type} {self.content_type}:{self.content_id}"


class SavedItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_items")
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    content_id = models.BigIntegerField()

    is_saved = models.BooleanField(default=False)
    saved_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    is_hidden = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "saved_items"
        constraints = [
            models.UniqueConstraint(fields=["user", "content_type", "content_id"], name="uq_saved_item"),
        ]

    def __str__(self):
        return (
            f"user_id={self.user_id} {self.content_type}:{self.content_id} "
            f"saved={self.is_saved} read={self.is_read} hidden={self.is_hidden}"
        )


class UserFollow(models.Model):
    """
    A user's follow of an entity, taxonomy topic, or source (M9) — feeds the
    two-stage ranker's candidate-generation stage (app/services/ranking_service.py)
    and is the substrate M10/M11 build person/entity pages and alerts on.

    `target_key` is a plain string, matched by convention against whichever
    pipeline-owned lookup table `target_type` names — same cross-ORM
    convention as UserExclusion.value, chosen per-type to match how that
    type is ALREADY referenced elsewhere in this codebase rather than
    inventing a new convention:
      - target_type="source" -> Source.key   (matches UserExclusion.value)
      - target_type="topic"  -> TaxonomyTopic.slug (matches Interest/TaxonomyTopic's shared vocabulary)
      - target_type="entity" -> str(Entity.id) (Entity has no slug; id is the only stable key)
    """

    TARGET_TYPE_CHOICES = [
        ("entity", "Entity"),
        ("topic", "Topic"),
        ("source", "Source"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follows")
    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES)
    target_key = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_follows"
        constraints = [
            models.UniqueConstraint(fields=["user", "target_type", "target_key"], name="uq_user_follow"),
        ]

    def __str__(self):
        return f"user_id={self.user_id} follows {self.target_type}:{self.target_key}"
