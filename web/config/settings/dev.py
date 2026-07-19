"""Local development settings."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# EMAIL_BACKEND is set in base.py — real Gmail SMTP if GMAIL_ADDRESS/
# GMAIL_APP_PASSWORD are configured in web/.env, console (prints instead of
# sending) otherwise. Not overridden here so a real dev environment with
# real credentials actually delivers mail.
