from django.urls import path

from .views import (
    ArticleDetailView,
    ArticleListView,
    VideoDetailView,
    VideoListView,
)

app_name = "news"

urlpatterns = [
    path("", ArticleListView.as_view(), name="article_list"),
    path("article/<int:pk>/", ArticleDetailView.as_view(), name="article_detail"),
    path("videos/", VideoListView.as_view(), name="video_list"),
    path("video/<int:pk>/", VideoDetailView.as_view(), name="video_detail"),
]
