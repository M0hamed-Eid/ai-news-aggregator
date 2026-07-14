"""
Backfills UserProfile + UserDigestSettings for users created before this
personalization schema existed (or created via createsuperuser, which
bypasses signals.py's usual post_save timing since it's just a regular
model save — the signal DOES fire for it too, but any user row inserted
before signals.py existed at all has no such history to trigger on).

signals.py handles brand-new signups going forward; this middleware is the
lazy, automatic safety net for everyone else so no manual DB fixes are ever
required — every authenticated request self-heals a missing profile.
"""
from .models import UserProfile


class EnsureUserProfileMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            profile = getattr(user, "profile", None)
            if profile is None:
                profile = UserProfile.objects.create(user=user)
            if getattr(profile, "digest_settings", None) is None:
                from apps.onboarding.models import UserDigestSettings

                UserDigestSettings.objects.create(profile=profile)
        return self.get_response(request)
