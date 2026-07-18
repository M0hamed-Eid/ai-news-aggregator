"""
Per-user personalization: personas, interests, digest settings, exclusions.

Onboarding here is SOFT/SKIPPABLE by design: nothing in this module gates
access on any of these rows existing or being filled in. UserProfile +
UserDigestSettings are auto-created with sensible defaults on signup (see
apps.accounts.signals), so a brand new user is immediately usable.

Exclude-list semantics are intentional: the ABSENCE of a UserExclusion row
means "included". A brand new user with zero exclusion rows gets everything;
there is no "seed all categories as included" step to run.
"""
from django.db import models


class Persona(models.Model):
    """A user-facing role/persona choice offered during onboarding (e.g. "Engineer")."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "personas"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Interest(models.Model):
    """A topic a user can follow (e.g. "Large Language Models").

    taxonomy_topic (M8): links to the pipeline-owned taxonomy_topics table
    (app/database/models/taxonomy_topic.py) via the read-only catalog mirror,
    matched by slug in a data migration — NOT a real cross-ORM FK, same
    db_constraint=False/DO_NOTHING convention as every other pipeline-mirror
    reference in this codebase (UserRanking.user, DigestClickToken.user,
    etc., just in the other direction). This is what lets user interests and
    content topics share ONE controlled vocabulary.
    """

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True, null=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    taxonomy_topic = models.ForeignKey(
        "catalog.TaxonomyTopic",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interests",
    )

    class Meta:
        db_table = "interests"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class UserInterest(models.Model):
    """A user's opt-in to a given Interest, with an optional relevance weight."""

    profile = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.CASCADE, related_name="interests"
    )
    interest = models.ForeignKey(
        Interest, on_delete=models.CASCADE, related_name="user_interests"
    )
    weight = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_interests"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "interest"], name="uq_profile_interest"
            )
        ]

    def __str__(self):
        return f"{self.profile.user.email} -> {self.interest.slug}"


class UserDigestSettings(models.Model):
    """
    Per-user digest delivery preferences. Auto-created (all defaults) on signup.

    Preferences v2 (M9): `expertise_level`/`content_depth` already existed but
    were previously INERT — recipients.py read them into UserProfile.preferences
    but CuratorAgent's prompt only ever used expertise_level as prose context,
    never as an actual ranking input (per Architecture Principle 10: "a
    preference nothing acts on is UI debt"). The two-stage ranker
    (app/services/ranking_service.py) now maps expertise_level to a target
    technical_depth band, finally making it load-bearing — so no new
    "difficulty" field was added here, the existing one was wired up instead.
    format_balance/topic_lean/reading_time_budget_minutes are genuinely new
    knobs the old CuratorAgent had no equivalent of.
    """

    profile = models.OneToOneField(
        "accounts.UserProfile", on_delete=models.CASCADE, related_name="digest_settings"
    )
    frequency = models.CharField(
        max_length=20, choices=[("daily", "Daily"), ("weekly", "Weekly")], default="daily"
    )
    max_items = models.IntegerField(default=10)
    is_paused = models.BooleanField(default=False)
    expertise_level = models.CharField(
        max_length=20,
        choices=[
            ("beginner", "Beginner"),
            ("intermediate", "Intermediate"),
            ("advanced", "Advanced"),
        ],
        default="intermediate",
    )
    content_depth = models.CharField(
        max_length=20,
        choices=[("technical", "Technical"), ("overview", "Overview")],
        default="technical",
    )
    format_balance = models.CharField(
        max_length=20,
        choices=[
            ("balanced", "Balanced"),
            ("articles", "Prefer articles"),
            ("videos", "Prefer videos"),
        ],
        default="balanced",
        help_text="Soft nudge on article vs. video mix in ranked results — never a hard filter.",
    )
    topic_lean = models.CharField(
        max_length=20,
        choices=[
            ("balanced", "Balanced"),
            ("research", "Research-leaning"),
            ("industry", "Industry-leaning"),
        ],
        default="balanced",
        help_text="Nudges ranking toward research-paper-style vs. product/industry-news content_category groupings.",
    )
    reading_time_budget_minutes = models.IntegerField(
        null=True, blank=True,
        help_text="Soft per-item time budget the ranker penalizes (not excludes) items against. Blank = no budget.",
    )

    class Meta:
        db_table = "user_digest_settings"

    def __str__(self):
        return f"DigestSettings({self.profile.user.email})"


class UserExclusion(models.Model):
    """
    A user's opt-out of a category or source.

    `value` is a plain string (a category slug like "government", or a
    Source.key like "reddit" from the SEPARATE SQLAlchemy pipeline in app/) —
    intentionally NOT a Django FK, since it references data owned by a
    different ORM/database boundary. Matches by string convention only.

    Absence of a row here means "included" — see the module docstring.
    """

    KIND_CHOICES = [("category", "Category"), ("source", "Source")]

    profile = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.CASCADE, related_name="exclusions"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    value = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_exclusions"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "kind", "value"], name="uq_profile_exclusion"
            )
        ]

    def __str__(self):
        return f"{self.profile.user.email} excludes {self.kind}:{self.value}"


class UserSourceSubscription(models.Model):
    """
    A user's opt-IN to a `visibility='user'` (user-submitted) Source (M10).

    This is the OPPOSITE polarity from UserExclusion: `visibility='global'`
    sources (the 9 admin-seeded ones) stay on-by-default for everyone,
    opt-out via UserExclusion, exactly as before M10. User-submitted
    sources can't default to "everyone gets it" the same way — nobody
    subscribed to a stranger's blog just because someone else added it —
    so they need a real positive opt-in row instead. Submitting a new
    source auto-creates a subscription for the submitter (see
    apps.onboarding.views's add-source flow); anyone ELSE can subscribe to
    an already-registered user-source via the same row shape, which is
    exactly what makes "one global source, two subscriptions" (the
    roadmap's own M10 success criterion) true.

    `source` FKs into the read-only `catalog.Source` mirror
    (db_constraint=False) purely for ORM ergonomics — same established
    pattern as Interest.taxonomy_topic — since `sources` is SQLAlchemy/
    pipeline-owned, not something Django migrates or writes.
    """

    profile = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.CASCADE, related_name="source_subscriptions",
    )
    source = models.ForeignKey(
        "catalog.Source", db_constraint=False, on_delete=models.CASCADE, related_name="subscriptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_source_subscriptions"
        constraints = [
            models.UniqueConstraint(fields=["profile", "source"], name="uq_profile_source_subscription"),
        ]

    def __str__(self):
        return f"{self.profile.user.email} subscribed to source_id={self.source_id}"
