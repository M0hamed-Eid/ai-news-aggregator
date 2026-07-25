"""
JSON API for the M15 frontend integration (see
.claude/plans/effervescent-petting-nebula.md) — mounted at /api/news/...
(config/urls.py). Every view here reuses the EXACT SAME querysets/services
apps.news.views' template-rendering counterparts already call
(HomeView/FeedView/SearchView) — no business logic is duplicated, only the
output format changes (JsonResponse instead of a rendered template).

Home/Feed/Search in the new frontend fetch a bounded set, then filter/search
client-side in-memory over whatever's been fetched so far. Feed/Search still
match the original "fetch once" model; Home (M15 Phase 5) additionally
supports real cursor-based pagination via HomeFeedAPIView's `before` param
(frontend/src/components/pages/HomePage.tsx's "Load more" button fetches
another page once the client-side reveal of the current batch is
exhausted) — the old unbounded Django ListView pagination
(news/article_list.html etc, M15 Phase 5 audit) had no 1:1 SPA equivalent
until this; query-param filtering (source/category/topic/q/from) is
otherwise unchanged, reusing HomeView's exact filter logic.
"""
from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.views import View

from apps.accounts.entitlements import user_can
from apps.behavior.models import SavedItem
from apps.behavior.services import attach_saved_state, mark_read
from apps.catalog.models import (
    Article, ContentScore, ContentTopic, Entity, Source, TaxonomyTopic, TrendReport, UserRanking, YoutubeVideo,
)
from apps.catalog.services import (
    attach_topics, get_chunks, get_cluster_member_count, get_full_story, get_hot_clusters, get_related_items,
    get_trending, get_user_visibility_source_keys, resolve_narrative_citations,
)
from apps.news.feed_ranking import content_type_for_item, diversify_home_items
from apps.news.search import semantic_search
from apps.onboarding.models import UserSourceSubscription

from .serializers import (
    LONG_VIDEO_THRESHOLD_SECONDS, serialize_detail, serialize_entity_detail, serialize_entity_summary, serialize_list,
)

# Bounded "recent window" for Home/Feed — these pages fetch once and filter
# client-side (see module docstring), so this caps real query/payload cost
# instead of ever shipping the entire catalog in one response.
DEFAULT_ITEMS_LIMIT = 300
MAX_ITEMS_LIMIT = 500
HOME_DIVERSITY_CANDIDATE_MULTIPLIER = 3


def _clamp_limit(request) -> int:
    try:
        limit = int(request.GET.get("limit", DEFAULT_ITEMS_LIMIT))
    except ValueError:
        limit = DEFAULT_ITEMS_LIMIT
    return max(1, min(limit, MAX_ITEMS_LIMIT))


def _apply_home_filters(request, articles, videos):
    """Mirrors apps.news.views.HomeView.get_queryset()'s filter block
    exactly — same param names, same semantics — so this endpoint is a
    drop-in replacement if/when the frontend switches to server-side
    filtering (not done in this phase; see module docstring)."""
    query = request.GET.get("q", "").strip()
    source = request.GET.get("source", "").strip()
    category = request.GET.get("category", "").strip()
    topic = request.GET.get("topic", "").strip()
    date_from = request.GET.get("from", "").strip()

    if source:
        articles = articles.filter(source=source)
        videos = videos if source == "youtube" else videos.none()
    if category:
        source_keys = list(Source.objects.filter(category=category).values_list("key", flat=True))
        articles = articles.filter(source__in=source_keys)
        videos = videos if category == "media" else videos.none()
    if topic:
        article_ids = list(
            ContentTopic.objects.filter(taxonomy_topic__slug=topic, content_type="article")
            .values_list("content_id", flat=True)
        )
        video_ids = list(
            ContentTopic.objects.filter(taxonomy_topic__slug=topic, content_type="youtube_video")
            .values_list("content_id", flat=True)
        )
        articles = articles.filter(pk__in=article_ids)
        videos = videos.filter(pk__in=video_ids)
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

    return articles, videos


def _quality_scores_for_items(items) -> dict:
    keys = [(content_type_for_item(item), item.pk) for item in items]
    if not keys:
        return {}

    article_ids = [content_id for content_type, content_id in keys if content_type == "article"]
    video_ids = [content_id for content_type, content_id in keys if content_type == "youtube_video"]
    query = Q()
    if article_ids:
        query |= Q(content_type="article", content_id__in=article_ids)
    if video_ids:
        query |= Q(content_type="youtube_video", content_id__in=video_ids)
    if not query:
        return {}

    return {
        (row.content_type, row.content_id): row.score
        for row in ContentScore.objects.filter(query)
    }


def _serialize_trending() -> list:
    """get_trending()'s (dimension, object, mention_count, multiplier) rows
    -> frontend TrendingTopic[] ({id, label, multiplier})."""
    return [
        {
            "id": f"{row['dimension']}:{row['object'].pk if row['dimension'] == 'entity' else row['object'].slug}",
            "label": row["object"].name,
            "multiplier": row["multiplier"],
        }
        for row in get_trending()
    ]


def _serialize_hot_clusters(user) -> list:
    """get_hot_clusters()'s rows -> a compact "N sources covering this
    story" strip for Home — restores the old home.html's SECOND trending
    mechanism (found missing during a live UI review): that template
    rendered a distinct row of up to 5 hot story-cluster pills alongside
    (not instead of) the topic/entity Trending pills. The Z.ai-authored
    SPA's HomePage.tsx only ever wired up the topic/entity one via
    _serialize_trending() above; get_hot_clusters() was never called from
    any Home-facing endpoint at all until now. Small, cheap default window
    (5 clusters / 48h) matching the old template's own usage."""
    clusters = get_hot_clusters(limit=5, hours=48)
    representatives = [c["representative"] for c in clusters]
    attach_saved_state(user, representatives)
    return [
        {
            "id": f"{'video' if getattr(rep, 'video_id', None) else 'article'}-{rep.pk}",
            "type": "video" if getattr(rep, "video_id", None) else "article",
            "title": rep.title,
            "memberCount": c["member_count"],
        }
        for c, rep in zip(clusters, representatives)
    ]


class HomeFeedAPIView(View):
    """GET /api/news/home/[?before=<ISO datetime>] — public, unpersonalized
    (matches HomeView's own access level). Same visibility rule as HomeView:
    sources with visibility='user' never appear here, subscribed or not.

    `before` is a cursor, not an offset — page N's request passes page
    (N-1)'s LAST (oldest) item's publishedAt, so "next page" means "items
    older than the oldest one already shown." Chosen over a numeric offset
    because articles/videos are two separate querysets merged and re-sorted
    in Python (see below) — an offset would have to be re-derived across
    both tables every time, while a timestamp cursor composes with the
    existing per-table `[:limit]` slicing trivially. `hasMore` tells the
    frontend whether a full page came back (there's likely more) so its
    "Load more" button knows when to stop, without the frontend needing to
    guess from a possibly-partial last page."""

    def get(self, request, *args, **kwargs):
        articles = Article.objects.exclude(source__in=get_user_visibility_source_keys())
        videos = YoutubeVideo.objects.all()
        articles, videos = _apply_home_filters(request, articles, videos)

        before = request.GET.get("before", "").strip()
        if before:
            try:
                cursor = datetime.fromisoformat(before.replace("Z", "+00:00"))
                articles = articles.filter(published_at__lt=cursor)
                videos = videos.filter(published_at__lt=cursor)
            except ValueError:
                pass

        limit = _clamp_limit(request)
        candidate_limit = min(MAX_ITEMS_LIMIT, max(limit + 1, limit * HOME_DIVERSITY_CANDIDATE_MULTIPLIER))
        # Fetch a wider recent pool, then diversify in Python. The first-stage
        # queryset is still recency-bounded; the second stage adds quality and
        # source penalties so one busy source cannot dominate the visible page.
        combined = list(articles[:candidate_limit + 1]) + list(videos[:candidate_limit + 1])
        combined.sort(key=lambda item: item.published_at, reverse=True)
        has_more = len(combined) > limit
        combined = diversify_home_items(combined, limit, quality_scores=_quality_scores_for_items(combined))

        attach_saved_state(request.user, combined)
        attach_topics(combined)

        # Just the 3 most recent items, no image/thumbnail gate. The
        # previous gate (`getattr(item, "image_url", None) or
        # hasattr(item, "thumbnail_url")`) was broken two ways: hasattr()
        # checks attribute EXISTENCE, not its value — thumbnail_url is a
        # YoutubeVideo @property that's always present (and always
        # non-empty, computed from video_id), so every video passed
        # unconditionally regardless of real content, while real dev data
        # confirms 0% of Article rows ever have a populated image_url, so
        # no article could ever pass. Net effect: Featured was 100% video
        # candidates whenever any recent video existed, and completely
        # empty whenever the top-12 window happened to contain none —
        # exactly the "empty unless filtered to YouTube" bug reported live.
        # Neither frontend card (HomePage.tsx's Featured grid, ArticleCard/
        # VideoCard) actually renders a real per-item photo anyway (a
        # decorative gradient regardless), so gating on image presence
        # never bought anything real to begin with.
        featured_candidates = combined[:3]

        return JsonResponse({
            "items": serialize_list(combined),
            "hasMore": has_more,
            "featured": serialize_list(featured_candidates),
            "trending": _serialize_trending(),
            "hotClusters": _serialize_hot_clusters(request.user),
            "sources": [
                {
                    "key": s.key, "name": s.name, "category": s.category_label,
                    "isActive": s.is_active, "isCustom": s.created_by is not None,
                }
                for s in Source.objects.filter(is_active=True).exclude(
                    key__in=get_user_visibility_source_keys()
                ).order_by("name")
            ],
            "categories": list(Source.CATEGORY_LABELS.values()),
            "topics": list(
                TaxonomyTopic.objects.filter(is_active=True).order_by("sort_order").values_list("name", flat=True)
            ),
        })


class FeedAPIView(LoginRequiredMixin, View):
    """GET /api/news/feed/ — personalized, reuses apps.news.views.FeedView's
    EXACT ranking-or-fallback query logic (kept in sync deliberately, not
    imported, since FeedView's version also builds a Django ListView
    pagination context this JSON view has no use for)."""

    def get(self, request, *args, **kwargs):
        user = request.user
        rankings = list(UserRanking.objects.filter(user_id=user.id).order_by("rank"))

        if rankings:
            has_ranking = True
            items = []
            for r in rankings:
                obj = r.content_object
                if obj is not None:
                    obj.rank = r.rank
                    obj.reasoning = r.reasoning
                    items.append(obj)
        else:
            has_ranking = False
            profile = user.profile
            excluded_sources = {e.value for e in profile.exclusions.filter(kind="source")}
            excluded_categories = {e.value for e in profile.exclusions.filter(kind="category")}
            category_source_keys = set(
                Source.objects.filter(category__in=excluded_categories).values_list("key", flat=True)
            ) if excluded_categories else set()
            excluded_all = excluded_sources | category_source_keys

            user_source_keys = get_user_visibility_source_keys()
            subscribed_keys = set(
                UserSourceSubscription.objects.filter(profile=profile).values_list("source__key", flat=True)
            )
            hidden_user_sources = user_source_keys - subscribed_keys

            articles = Article.objects.exclude(source__in=excluded_all).exclude(source__in=hidden_user_sources)
            videos = (
                YoutubeVideo.objects.all()
                if "media" not in excluded_categories and "youtube" not in excluded_all
                else YoutubeVideo.objects.none()
            )
            items = list(articles) + list(videos)
            items.sort(key=lambda item: item.published_at, reverse=True)

        limit = _clamp_limit(request)
        items = items[:limit]
        attach_saved_state(user, items)
        attach_topics(items)

        return JsonResponse({"items": serialize_list(items), "hasRanking": has_ranking})


class SearchAPIView(View):
    """GET /api/news/search/?q=... — public (matches SearchView's own access
    level), real pgvector semantic search via apps.news.search.semantic_search
    (M9), with a keyword-search fallback already built into that function."""

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        if not query:
            return JsonResponse({"items": [], "usedSemantic": True})

        results, used_semantic = semantic_search(query, limit=60)
        attach_saved_state(request.user, results)
        attach_topics(results)

        return JsonResponse({"items": serialize_list(results), "usedSemantic": used_semantic})


class ArticleDetailAPIView(LoginRequiredMixin, View):
    """GET /api/news/articles/<int:pk>/ — mirrors apps.news.views.ArticleDetailView
    field-for-field: same related-items logic (cluster membership first,
    same-source fallback), same mark_read() side effect on every GET."""

    def get(self, request, pk, *args, **kwargs):
        article = Article.objects.filter(pk=pk).exclude(source__in=get_user_visibility_source_keys()).first()
        if article is None:
            return JsonResponse({"error": "article not found"}, status=404)

        related = get_related_items("article", article.pk, limit=4)
        if not related:
            related = list(
                Article.objects.filter(source=article.source).exclude(pk=article.pk).order_by("-published_at")[:4]
            )
        attach_saved_state(request.user, related)
        attach_topics(related)

        mark_read(request.user, "article", article.pk)

        data = serialize_detail(article, request_user=request.user)
        data["related"] = serialize_list(related)
        data["clusterMemberCount"] = get_cluster_member_count("article", article.pk)
        return JsonResponse(data)


class VideoDetailAPIView(LoginRequiredMixin, View):
    """GET /api/news/videos/<int:pk>/ — mirrors apps.news.views.VideoDetailView:
    same chapters gate (Pro-only for videos >= LONG_VIDEO_THRESHOLD_SECONDS,
    a 200-OK upsell shape rather than a 403 — see VideoItem.chapters being
    simply omitted/empty for a non-Pro viewer, same precedent as
    TrendReportView), same related-items logic (NO same-channel fallback,
    matching that view's own comment), same mark_read() side effect."""

    def get(self, request, pk, *args, **kwargs):
        video = YoutubeVideo.objects.filter(pk=pk).first()
        if video is None:
            return JsonResponse({"error": "video not found"}, status=404)

        related = get_related_items("youtube_video", video.pk, limit=4)
        attach_saved_state(request.user, related)
        attach_topics(related)

        is_long_video = bool(video.duration_seconds and video.duration_seconds >= LONG_VIDEO_THRESHOLD_SECONDS)
        can_view_chapters = user_can(request.user, "deep_video_summaries")
        # Fetch chunks whenever the video qualifies, REGARDLESS of
        # entitlement — the frontend's "Chapters (N)" header + its
        # chapters.length>0 gate need a real count to show the "N chapters,
        # upgrade to Pro" teaser to a free viewer (matching this page's
        # original design intent: a locked preview, not a vanished section).
        # Only the CONTENT is redacted below for a non-entitled viewer, never
        # the count -- title/summary text is the actual paywalled asset.
        chunks = get_chunks("youtube_video", video.pk) if is_long_video else []

        mark_read(request.user, "youtube_video", video.pk)

        data = serialize_detail(video, request_user=request.user)
        data["clusterMemberCount"] = get_cluster_member_count("youtube_video", video.pk)
        data["chapters"] = [
            {
                "title": c.chapter_title if can_view_chapters else "",
                "startTime": c.start_seconds if can_view_chapters else 0,
                "summary": c.chunk_summary if can_view_chapters else "",
            }
            for c in chunks
        ]
        data["related"] = serialize_list(related)
        # Lets the frontend distinguish "long video, Pro required" from
        # "short video, nothing to show" without re-deriving the threshold
        # client-side — a plain bool the UI already has a precedent for
        # gating on (see web/apps/news/views.py's identical is_long_video/
        # can_view_chapters pair).
        data["isLongVideo"] = is_long_video
        data["canViewChapters"] = can_view_chapters
        return JsonResponse(data)


class EntityDetailAPIView(LoginRequiredMixin, View):
    """GET /api/news/entities/<int:pk>/ — mirrors apps.news.views.EntityDetailView,
    reusing the exact same apps.catalog.services helpers."""

    def get(self, request, pk, *args, **kwargs):
        entity = Entity.objects.filter(pk=pk).first()
        if entity is None:
            return JsonResponse({"error": "entity not found"}, status=404)
        return JsonResponse(serialize_entity_detail(entity, request_user=request.user))


class PeopleAPIView(LoginRequiredMixin, View):
    """GET /api/news/people/?q=... — mirrors apps.news.views.PeopleListView
    (entity_type='person', name search), light shape (no mentionData/
    ownOutput/mentions — those are detail-page-only, see
    serializers.serialize_entity_summary)."""

    def get(self, request, *args, **kwargs):
        from apps.behavior.services import get_followed_keys

        qs = Entity.objects.filter(entity_type="person").order_by("name")
        query = request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(name__icontains=query)

        followed_keys = get_followed_keys(request.user, "entity")
        people = [serialize_entity_summary(e, followed_keys=followed_keys) for e in qs[:200]]
        return JsonResponse({"people": people})


class LibraryAPIView(LoginRequiredMixin, View):
    """GET /api/news/library/ — mirrors apps.behavior.views.LibraryView's
    exact resolve-SavedItem-rows-to-real-objects logic. Lives here (not in
    apps.behavior) purely to avoid a circular import: apps.news already
    depends one-way on apps.behavior.services (attach_saved_state/mark_read),
    and this view needs apps.news.serializers.serialize_list — putting it in
    apps.behavior would require the reverse import too."""

    def _resolve(self, saved_items_qs):
        resolved = []
        for saved in saved_items_qs:
            model = Article if saved.content_type == "article" else YoutubeVideo
            obj = model.objects.filter(pk=saved.content_id).first()
            if obj is not None:
                obj.is_saved = saved.is_saved
                obj.is_hidden = saved.is_hidden
                obj.is_read = saved.is_read
                resolved.append(obj)
        return resolved

    def get(self, request, *args, **kwargs):
        saved_items = self._resolve(
            SavedItem.objects.filter(user=request.user, is_saved=True).order_by("-saved_at")
        )
        read_items = self._resolve(
            SavedItem.objects.filter(user=request.user, is_read=True).order_by("-read_at")
        )
        for bucket in (saved_items, read_items):
            attach_topics(bucket)
        return JsonResponse({
            "savedItems": serialize_list(saved_items),
            "readItems": serialize_list(read_items),
        })


class InsightsAPIView(LoginRequiredMixin, View):
    """GET /api/news/insights/ — mirrors apps.news.views.TrendReportView
    field-for-field (same Pro gate via user_can(..., "trend_narrative"),
    same TrendReport.objects.order_by("-week_start_date").first() query,
    same resolve_narrative_citations() call), for the recreated
    InsightsPage.tsx to replace its INSIGHTS mock import with."""

    def get(self, request, *args, **kwargs):
        can_view = user_can(request.user, "trend_narrative")
        if not can_view:
            return JsonResponse({"canView": False, "weekOf": None, "generatedAt": None, "insights": []})

        report = TrendReport.objects.order_by("-week_start_date").first()
        if report is None:
            return JsonResponse({"canView": True, "weekOf": None, "generatedAt": None, "insights": []})

        claims = resolve_narrative_citations(report.narrative)
        insights = [
            {
                "id": f"insight-{i}",
                "headline": claim.get("headline", ""),
                "summary": claim.get("body", ""),
                "sources": [
                    {
                        "id": f"{'video' if getattr(item, 'video_id', None) else 'article'}-{item.pk}",
                        "title": item.title,
                    }
                    for item in claim.get("citation_items", [])
                ],
            }
            for i, claim in enumerate(claims)
        ]
        return JsonResponse({
            "canView": True,
            "weekOf": report.week_start_date.isoformat(),
            "generatedAt": report.generated_at.isoformat(),
            "insights": insights,
        })


class StoryClusterAPIView(LoginRequiredMixin, View):
    """GET /api/news/story/<content_type>/<content_id>/ — mirrors
    apps.news.views.StoryClusterView field-for-field (same get_full_story()
    call, same 404-if-item-missing / honest-empty-if-not-clustered
    semantics), for the recreated StoryClusterPage.tsx. The anchor item is
    NOT split out server-side -- it's just the member whose id matches the
    URL's content_type/content_id, same convention api.ts's
    parseContentRef() already uses (frontend finds it via
    `${type}-${id}` against the returned items list)."""

    def get(self, request, content_type, content_id, *args, **kwargs):
        if content_type not in ("article", "youtube_video"):
            return JsonResponse({"error": "unknown content type"}, status=404)

        model = YoutubeVideo if content_type == "youtube_video" else Article
        anchor = model.objects.filter(pk=content_id).first()
        if anchor is None:
            return JsonResponse({"error": "item not found"}, status=404)

        members = get_full_story(content_type, content_id)
        attach_saved_state(request.user, members)
        attach_topics(members)

        return JsonResponse({
            "anchorId": f"{'video' if content_type == 'youtube_video' else 'article'}-{content_id}",
            "items": serialize_list(members),
        })


class ClusterListAPIView(LoginRequiredMixin, View):
    """GET /api/news/clusters/?hours=48|168|720 — mirrors
    apps.news.views.ClusterListView field-for-field (same get_hot_clusters()
    call, same HOUR_PRESETS/DEFAULT_HOURS), for the recreated "Trending
    Stories" SPA page. The old news/cluster_list.html had ZERO SPA
    equivalent until this (M15 Phase 5 audit finding) — StoryClusterPage.tsx
    only ever shows one already-known cluster, it's not a discovery surface."""

    HOUR_PRESETS = [(48, "Last 48 hours"), (168, "Last 7 days"), (720, "Last 30 days")]
    DEFAULT_HOURS = 168

    def get(self, request, *args, **kwargs):
        valid_hours = {h for h, _ in self.HOUR_PRESETS}
        try:
            hours = int(request.GET.get("hours", self.DEFAULT_HOURS))
        except ValueError:
            hours = self.DEFAULT_HOURS
        if hours not in valid_hours:
            hours = self.DEFAULT_HOURS

        clusters = get_hot_clusters(limit=30, hours=hours)
        representatives = [c["representative"] for c in clusters]
        attach_saved_state(request.user, representatives)
        attach_topics(representatives)
        serialized_reps = serialize_list(representatives)

        return JsonResponse({
            "activeHours": hours,
            "hourPresets": [{"hours": h, "label": label} for h, label in self.HOUR_PRESETS],
            "clusters": [
                {"memberCount": c["member_count"], "representative": rep}
                for c, rep in zip(clusters, serialized_reps)
            ],
        })
