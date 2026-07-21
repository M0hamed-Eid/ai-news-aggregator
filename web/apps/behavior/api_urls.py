from django.urls import path

from .api_views import FollowsStateAPIView, FollowToggleAPIView

app_name = "behavior_api"

urlpatterns = [
    path("follows/", FollowsStateAPIView.as_view(), name="follows_state"),
    path("follow/", FollowToggleAPIView.as_view(), name="follow_toggle"),
]
