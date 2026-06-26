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
