from django.urls import path

from .views import EventIngestView, HideToggleView, LibraryView, SaveToggleView

app_name = "behavior"

urlpatterns = [
    path("events/", EventIngestView.as_view(), name="events"),
    path("save/", SaveToggleView.as_view(), name="save"),
    path("hide/", HideToggleView.as_view(), name="hide"),
    path("library/", LibraryView.as_view(), name="library"),
]
