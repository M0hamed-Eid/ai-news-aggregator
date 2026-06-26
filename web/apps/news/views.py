"""
News browsing — read-only over the pipeline's `catalog` tables.

Two content types share the same browsing UX:
  * Article       (table: articles)
  * YoutubeVideo  (table: youtube_videos)

No models of its own. Search is a simple case-insensitive match for now;
Postgres full-text search is a Phase 2 improvement.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import DetailView, ListView

from apps.catalog.models import Article, YoutubeVideo

from .utils import render_body


class ArticleListView(LoginRequiredMixin, ListView):
    model = Article
    template_name = "news/article_list.html"
    context_object_name = "articles"
    paginate_by = 9

    def get_queryset(self):
        qs = Article.objects.all()  # ordered by -published_at (model Meta)
        source = self.request.GET.get("source", "").strip()
        if source:
            qs = qs.filter(source=source)
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(author__icontains=query)
                | Q(tags__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "").strip()
        ctx["active_source"] = self.request.GET.get("source", "").strip()
        ctx["sources"] = [
            {"code": code, "label": label}
            for code, label in Article.SOURCE_LABELS.items()
        ]
        return ctx


class ArticleDetailView(LoginRequiredMixin, DetailView):
    model = Article
    template_name = "news/article_detail.html"
    context_object_name = "article"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["source_label"] = self.object.source_label
        ctx["body"] = render_body(self.object.content)
        return ctx


class VideoListView(LoginRequiredMixin, ListView):
    model = YoutubeVideo
    template_name = "news/video_list.html"
    context_object_name = "videos"
    paginate_by = 9

    def get_queryset(self):
        qs = YoutubeVideo.objects.all()  # ordered by -published_at (model Meta)
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(channel_name__icontains=query)
                | Q(tags__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "").strip()
        return ctx


class VideoDetailView(LoginRequiredMixin, DetailView):
    model = YoutubeVideo
    template_name = "news/video_detail.html"
    context_object_name = "video"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["transcript"] = render_body(self.object.content)
        return ctx
