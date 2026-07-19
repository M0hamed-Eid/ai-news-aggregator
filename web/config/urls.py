from django.contrib import admin
from django.urls import include, path

from apps.accounts.ops import OpsDashboardView
from apps.accounts.views import PricingView
from apps.behavior.views import DigestRedirectView
from apps.news.views import EntityDetailView, FeedView, HomeView, SearchView, TrendReportView

urlpatterns = [
    path("admin/", admin.site.urls),
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
