# web/apps/accounts/email_verification.py
#
# M13 — email verification. Soft-gated for app usage (a new user can browse
# immediately, matching the established UserProfile.onboarding_completed
# convention), but hard-required before Stripe checkout (see views.py's
# CreateCheckoutSessionView) — this directly matches success criterion 1's
# literal ordering ("verifies email, upgrades via Stripe").
#
# EmailVerificationTokenGenerator deliberately does NOT reuse Django's
# `django.contrib.auth.tokens.default_token_generator` directly, even though
# it's the exact same one-time-token MECHANISM password reset already uses
# (and this class still subclasses it) — that generator's hash includes
# `user.last_login`, which is correct for password-reset (a token should die
# the moment you log in again) but wrong here: a user who signs up, logs out,
# and logs back in a day later before clicking yesterday's verification email
# would find the link "invalid" for no real reason. Swapping last_login for
# email_verified in the hash fixes that AND gives the token a natural
# self-invalidation once used (no separate consumed-token table needed) —
# still Django's own token algorithm, just one field corrected for this reuse.

import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_verified}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()


def send_verification_email(user, request) -> bool:
    """
    Returns True if the email was handed off successfully (accepted by the
    SMTP server, or printed via the console backend), False on a real
    delivery failure. Logs the failure explicitly rather than swallowing it
    silently — matches app/services/email_sender.py's own "log the error,
    return False, never crash the caller" discipline instead of Django's
    fail_silently=True (which would report NOTHING on a real SMTP error:
    wrong credentials, Gmail rate limit, network issue, etc).
    """
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    path = reverse("accounts:verify_email", kwargs={"uidb64": uidb64, "token": token})
    verify_url = request.build_absolute_uri(path)

    body = render_to_string(
        "registration/verification_email.txt", {"user": user, "verify_url": verify_url},
    )
    try:
        send_mail(
            subject="Verify your AI Compass email",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("send_verification_email: failed to send to %s", user.email)
        return False
