from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path

from apps.accounts.api_views import SessionView
from apps.behavior.views import DigestRedirectView


def healthz(request):
    """Plain liveness+DB-connectivity check — used by Caddy/monitoring and
    documented as the production health-check endpoint. Deliberately no
    auth/rate-limit: it carries no sensitive data, just a status code."""
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("api/session/", SessionView.as_view(), name="api_session"),
    path("api/accounts/", include("apps.accounts.api_urls")),
    path("api/news/", include("apps.news.api_urls")),
    path("api/onboarding/", include("apps.onboarding.api_urls")),
    path("api/behavior/", include("apps.behavior.api_urls")),
    # M15 Phase 5 — home/feed/search/entity/insights/pricing/ops (root-mounted
    # Django template views) and the whole apps.news/apps.onboarding
    # template-rendering surfaces are retired: every one of these paths was
    # already unreachable in this deployment topology (see docker/Caddyfile +
    # frontend/next.config.ts's DJANGO_PREFIXES — only /api/*, /admin/*,
    # /accounts/*, /onboarding/*, /behavior/*, /assistant/*, /healthz/*,
    # /r/*, /static/* are proxied to Django; everything else, including all
    # of these, falls through to the Next.js frontend container
    # unconditionally), and the SPA (frontend/) has a real, fully-wired
    # replacement for every one of them.
    path("accounts/", include("apps.accounts.urls")),
    path("behavior/", include("apps.behavior.urls")),
    path("assistant/", include("apps.assistant.urls")),
    path("r/<str:token>/", DigestRedirectView.as_view(), name="digest_redirect"),
]
