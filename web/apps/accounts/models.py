from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractUser):
    """
    Custom user that authenticates with email instead of username.

    Django owns this table (`users`). The pipeline never reads or writes it.
    Set as AUTH_USER_MODEL from the very first migration so it can never be
    swapped out painfully later.
    """

    class Plan(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"

    username = None  # drop the username field entirely
    email = models.EmailField(_("email address"), unique=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    plan_expires_at = models.DateTimeField(null=True, blank=True)
    # M13 — soft-gated: never blocks basic app access (same convention as
    # UserProfile.onboarding_completed), but hard-required before Stripe
    # checkout (see apps.accounts.views.CreateCheckoutSessionView).
    email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # createsuperuser prompts for email + password

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email


class UserProfile(models.Model):
    """
    Per-user personalization anchor.

    One-to-one with User. Onboarding is SOFT/SKIPPABLE: a brand new user gets
    this row (via the post_save signal in signals.py) with persona=None and
    onboarding_completed=False, but nothing in the app gates access on it —
    sensible defaults apply immediately and the user can complete onboarding
    whenever (or never).
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(blank=True, default="")
    persona = models.ForeignKey(
        "onboarding.Persona",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profiles",
    )
    onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"

    def __str__(self):
        return f"Profile({self.user.email})"


class StripeCustomer(models.Model):
    """
    M13 — Stripe customer/subscription mapping (Django-owned per
    docs/ROADMAP.md's M13 spec). This is bookkeeping ONLY — every
    entitlement check in the app (user_can(), FEATURE_PLANS, M11's
    DjangoUser pipeline mirror) keeps reading the SAME User.plan/
    plan_expires_at fields it always has. The Stripe webhook
    (apps.accounts.billing.StripeWebhookView) is the only writer of this
    table AND the only thing that flips User.plan/plan_expires_at — nothing
    else in the app ever sets Pro directly.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="stripe_customer")
    stripe_customer_id = models.CharField(max_length=255, unique=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    # Stripe's own status strings verbatim: active, trialing, past_due,
    # canceled, unpaid, incomplete, incomplete_expired — never re-enumerated
    # here, since Stripe is the source of truth for what these mean.
    subscription_status = models.CharField(max_length=50, null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stripe_customers"

    def __str__(self):
        return f"StripeCustomer({self.user.email})"


class TermsAcceptance(models.Model):
    """
    M16 — auditable record of which Terms/Privacy version a user accepted
    and when. APPEND-ONLY like UserEvent (apps.behavior.models) — a new
    acceptance is a new row, never an update, so the full history survives
    a re-acceptance after a version bump (deliberately NOT one row per user
    overwritten in place, matching the ask: "know which version a user
    accepted", not just the latest). Intentionally minimal fields — no IP,
    no user-agent, nothing beyond what's needed to answer "did user X
    accept version Y, and when."
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="terms_acceptances")
    terms_version = models.CharField(max_length=20)
    privacy_policy_version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "terms_acceptances"
        indexes = [models.Index(fields=["user", "-accepted_at"], name="ix_terms_acceptance_user")]

    def __str__(self):
        return f"TermsAcceptance(user_id={self.user_id}, terms={self.terms_version}, at={self.accepted_at})"
