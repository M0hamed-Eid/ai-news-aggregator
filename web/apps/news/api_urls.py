from django.urls import path

from .api_views import (
    ArticleDetailAPIView, ClusterListAPIView, EntityDetailAPIView, FeedAPIView, HomeFeedAPIView, InsightsAPIView,
    LibraryAPIView, PeopleAPIView, SearchAPIView, StoryClusterAPIView, VideoDetailAPIView,
)

app_name = "news_api"

urlpatterns = [
    path("home/", HomeFeedAPIView.as_view(), name="home"),
    path("feed/", FeedAPIView.as_view(), name="feed"),
    path("search/", SearchAPIView.as_view(), name="search"),
    path("articles/<int:pk>/", ArticleDetailAPIView.as_view(), name="article_detail"),
    path("videos/<int:pk>/", VideoDetailAPIView.as_view(), name="video_detail"),
    path("entities/<int:pk>/", EntityDetailAPIView.as_view(), name="entity_detail"),
    path("people/", PeopleAPIView.as_view(), name="people"),
    path("library/", LibraryAPIView.as_view(), name="library"),
    path("insights/", InsightsAPIView.as_view(), name="insights"),
    path("story/<str:content_type>/<int:content_id>/", StoryClusterAPIView.as_view(), name="story_cluster"),
    path("clusters/", ClusterListAPIView.as_view(), name="cluster_list"),
]
