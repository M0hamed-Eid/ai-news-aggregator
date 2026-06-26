"""Local development settings."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# Print emails (password reset, etc.) to the console during development.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
