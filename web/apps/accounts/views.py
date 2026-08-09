from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View

from apps.behavior.ratelimit import check_rate_limit

from .email_verification import email_verification_token, send_verification_email
from .models import User

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 300


def frontend_redirect(path: str):
    """redirect() to a frontend PAGE (as opposed to a Django URL name) —
    "/", "/login", "/billing", "/pricing", etc. On a split-domain deploy
    (Vercel+Render) that page only exists on settings.FRONTEND_BASE_URL,
    NOT on Django's own domain — a bare redirect(path) 404s there (found
    live, see prod.py's FRONTEND_BASE_URL comment for the real traceback).
    On the same-origin Oracle/Caddy path and local dev's proxied :3000/:8000
    split, this still resolves correctly; FRONTEND_BASE_URL is genuinely
    "" only on Oracle prod, where the relative redirect is already right."""
    base = getattr(settings, "FRONTEND_BASE_URL", "")
    return redirect(f"{base}{path}" if base else path)


def login_rate_limit_ok(request, email: str) -> bool:
    """
    Shared budget for the real JSON LoginAPIView (apps.accounts.api_views) —
    the classic RateLimitedLoginView that used to call this too was retired
    in M15 Phase 5 (login.html superseded by LoginPage.tsx), but this stays
    as the single source of truth for the login rate limit. Keyed on BOTH
    the client IP (blocks distributed brute force) and the submitted email
    (blocks a targeted attack against one account from many IPs) — every
    call consumes from both budgets regardless of whether the credentials
    turn out to be valid.
    """
    ip = request.META.get("REMOTE_ADDR") or "unknown"
    ip_ok = check_rate_limit(f"login_attempt:ip:{ip}", LOGIN_ATTEMPT_LIMIT, LOGIN_ATTEMPT_WINDOW_SECONDS)
    email_ok = (
        check_rate_limit(f"login_attempt:email:{email}", LOGIN_ATTEMPT_LIMIT, LOGIN_ATTEMPT_WINDOW_SECONDS)
        if email else True
    )
    return ip_ok and email_ok


class VerifyEmailView(View):
    """GET /accounts/verify/<uidb64>/<token>/ — the link sent by send_verification_email()."""

    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and email_verification_token.check_token(user, token):
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            messages.success(request, "Your email is verified.")
        else:
            messages.error(request, "That verification link is invalid or has already been used.")

        return frontend_redirect("/" if request.user.is_authenticated else "/login")
