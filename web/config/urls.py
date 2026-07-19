from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path

from apps.accounts.ops import OpsDashboardView
from apps.accounts.views import PricingView
from apps.behavior.views import DigestRedirectView
from apps.news.views import EntityDetailView, FeedView, HomeView, SearchView, TrendReportView


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
    path("", HomeView.as_view(), name="home"),
    path("feed/", FeedView.as_view(), name="feed"),
    path("search/", SearchView.as_view(), name="search"),
    path("entity/<int:pk>/", EntityDetailView.as_view(), name="entity_detail"),
    path("insights/", TrendReportView.as_view(), name="insights"),
    path("pricing/", PricingView.as_view(), name="pricing"),
    path("ops/", OpsDashboardView.as_view(), name="ops_dashboard"),
    path("accounts/", include("apps.accounts.urls")),
    path("news/", include("apps.news.urls")),
    path("onboarding/", include("apps.onboarding.urls")),
    path("behavior/", include("apps.behavior.urls")),
    path("r/<str:token>/", DigestRedirectView.as_view(), name="digest_redirect"),
]
