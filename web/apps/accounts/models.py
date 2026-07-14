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

    username = None  # drop the username field entirely
    email = models.EmailField(_("email address"), unique=True)

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
