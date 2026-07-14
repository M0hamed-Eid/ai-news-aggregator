"""
News browsing — read-only over the pipeline's `catalog` tables.

Two content types share the same browsing UX:
  * Article       (table: articles)
  * YoutubeVideo  (table: youtube_videos)

No models of its own. Search is a simple case-insensitive match for now;
Postgres full-text search is a Phase 2 improvement.

HomeView and FeedView also live here (not a separate app) — same domain
(browsing catalog content), just two different entry points: Home is the
public, unpersonalized "what's happening" page; Feed is the login-gated,
personalized one. Both are wired at the project root in config/urls.py
(alongside the pre-existing `home` route), not under this app's own
`news:` namespace.
"""
from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import DetailView, ListView

from apps.behavior.services import attach_saved_state, mark_read
from apps.catalog.models import Article, Source, UserRanking, YoutubeVideo


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
        ctx["reasoning"] = _recommendation_reasoning(self.request.user, "article", self.object.pk)
        related = list(
            Article.objects.filter(source=self.object.source)
            .exclude(pk=self.object.pk)
            .order_by("-published_at")[:4]
        )
        attach_saved_state(self.request.user, related)
        ctx["related"] = related
        mark_read(self.request.user, "article", self.object.pk)
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
        ctx["reasoning"] = _recommendation_reasoning(self.request.user, "youtube_video", self.object.pk)
        mark_read(self.request.user, "youtube_video", self.object.pk)
        return ctx


def _recommendation_reasoning(user, content_type, content_id):
    """CuratorAgent's own stated reasoning for this user+item, if a ranking exists — not synthesized."""
    if not user.is_authenticated:
        return None
    ranking = UserRanking.objects.filter(
        user_id=user.id, content_type=content_type, content_id=content_id
    ).first()
    return ranking.reasoning if ranking else None


class HomeView(ListView):
    """
    Public, NOT personalized — the same content everyone sees, newest first.
    Combines Article + YoutubeVideo (two querysets, no shared table) into one
    sorted Python list; Paginator works fine over a plain list.
    """

    template_name = "home.html"
    context_object_name = "items"
    paginate_by = 12

    def get_queryset(self):
        articles = Article.objects.all()
        videos = YoutubeVideo.objects.all()

        query = self.request.GET.get("q", "").strip()
        source = self.request.GET.get("source", "").strip()
        category = self.request.GET.get("category", "").strip()
        date_from = self.request.GET.get("from", "").strip()

        if source:
            articles = articles.filter(source=source)
            videos = videos if source == "youtube" else videos.none()
        if category:
            source_keys = list(Source.objects.filter(category=category).values_list("key", flat=True))
            articles = articles.filter(source__in=source_keys)
            videos = videos if category == "media" else videos.none()
        if query:
            articles = articles.filter(
                Q(title__icontains=query) | Q(summary__icontains=query) | Q(author__icontains=query)
            )
            videos = videos.filter(
                Q(title__icontains=query) | Q(summary__icontains=query) | Q(channel_name__icontains=query)
            )
        if date_from:
            try:
                parsed = datetime.strptime(date_from, "%Y-%m-%d")
                articles = articles.filter(published_at__date__gte=parsed.date())
                videos = videos.filter(published_at__date__gte=parsed.date())
            except ValueError:
                pass

        combined = list(articles) + list(videos)
        combined.sort(key=lambda item: item.published_at, reverse=True)
        self._all_items = combined
        return combined

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        featured = [item for item in self._all_items[:12] if getattr(item, "image_url", None) or hasattr(item, "thumbnail_url")][:3]
        # attach_saved_state is safe here even though `featured` isn't the
        # paginated page — it's already a small fixed slice ([:12] then
        # [:3]), not the full unpaginated result set.
        attach_saved_state(self.request.user, featured)
        attach_saved_state(self.request.user, ctx["items"])
        ctx.update({
            "q": self.request.GET.get("q", "").strip(),
            "active_source": self.request.GET.get("source", "").strip(),
            "active_category": self.request.GET.get("category", "").strip(),
            "date_from": self.request.GET.get("from", "").strip(),
            "sources": Source.objects.filter(is_active=True).order_by("name"),
            "categories": Source.CATEGORY_LABELS.items(),
            "featured": featured,
        })
        return ctx


class FeedView(LoginRequiredMixin, ListView):
    """
    Personalized — reads the persisted output of CuratorAgent's ranking pass
    (catalog.UserRanking, written by app/services/digest_service.py). Django
    never ranks anything itself; it only reads what the batch pipeline
    already computed for THIS user's last digest run.

    Fallback for users with no ranking yet (never had a digest run): plain
    date-ordered content with their own exclusions applied — an honest empty
    state, not fake personalization.
    """

    template_name = "feed.html"
    context_object_name = "items"
    paginate_by = 12

    def get_queryset(self):
        rankings = list(
            UserRanking.objects.filter(user_id=self.request.user.id).order_by("rank")
        )
        if rankings:
            self._has_ranking = True
            items = []
            for r in rankings:
                obj = r.content_object
                if obj is not None:
                    obj.rank = r.rank
                    obj.reasoning = r.reasoning
                    items.append(obj)
            return items

        self._has_ranking = False
        profile = self.request.user.profile
        excluded_sources = {e.value for e in profile.exclusions.filter(kind="source")}
        excluded_categories = {e.value for e in profile.exclusions.filter(kind="category")}
        category_source_keys = set(
            Source.objects.filter(category__in=excluded_categories).values_list("key", flat=True)
        ) if excluded_categories else set()
        excluded_all = excluded_sources | category_source_keys

        articles = Article.objects.exclude(source__in=excluded_all)
        videos = YoutubeVideo.objects.all() if "media" not in excluded_categories and "youtube" not in excluded_all else YoutubeVideo.objects.none()
        combined = list(articles) + list(videos)
        combined.sort(key=lambda item: item.published_at, reverse=True)
        return combined

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_ranking"] = self._has_ranking
        attach_saved_state(self.request.user, ctx["items"])
        return ctx
