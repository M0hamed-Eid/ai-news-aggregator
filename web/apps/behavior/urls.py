from django.urls import path

from .views import EventIngestView, FollowToggleView, HideToggleView, SaveToggleView

app_name = "behavior"

urlpatterns = [
    path("events/", EventIngestView.as_view(), name="events"),
    path("save/", SaveToggleView.as_view(), name="save"),
    path("hide/", HideToggleView.as_view(), name="hide"),
    path("follow/", FollowToggleView.as_view(), name="follow"),
    # library/ (LibraryView) retired in M15 Phase 5 — LibraryAPIView
    # (apps.news.api_views, its own docstring confirms exact-logic parity)
    # + LibraryPage.tsx replace it entirely.
]
