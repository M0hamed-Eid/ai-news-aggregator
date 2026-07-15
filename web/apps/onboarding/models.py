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
    """Per-user digest delivery preferences. Auto-created (all defaults) on signup."""

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
