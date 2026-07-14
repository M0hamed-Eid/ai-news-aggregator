from django.contrib import admin
from django.urls import include, path

from apps.news.views import FeedView, HomeView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", HomeView.as_view(), name="home"),
    path("feed/", FeedView.as_view(), name="feed"),
    path("accounts/", include("apps.accounts.urls")),
    path("news/", include("apps.news.urls")),
    path("onboarding/", include("apps.onboarding.urls")),
]
