from django.urls import path

from .views import (
    ArticleDetailView,
    ArticleListView,
    PeopleListView,
    StoryClusterView,
    VideoDetailView,
    VideoListView,
)

app_name = "news"

urlpatterns = [
    path("", ArticleListView.as_view(), name="article_list"),
    path("article/<int:pk>/", ArticleDetailView.as_view(), name="article_detail"),
    path("videos/", VideoListView.as_view(), name="video_list"),
    path("video/<int:pk>/", VideoDetailView.as_view(), name="video_detail"),
    path("people/", PeopleListView.as_view(), name="people_list"),
    path("story/<str:content_type>/<int:content_id>/", StoryClusterView.as_view(), name="story_cluster"),
    # EntityDetailView (M11) is registered at the project root as
    # `entity_detail` (config/urls.py), not here — see that view's docstring.
]
