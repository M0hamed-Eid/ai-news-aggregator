"""
News browsing — read-only over the pipeline's `catalog` tables.

Two content types share the same browsing UX:
  * Article       (table: articles)
  * YoutubeVideo  (table: youtube_videos)

No models of its own. Home/Feed/News-list search is a simple case-insensitive
`icontains` match. SearchView (M9) is the exception — real pgvector semantic
search, with a keyword-search fallback (see apps.news.search.semantic_search).

HomeView and FeedView also live here (not a separate app) — same domain
(browsing catalog content), just two different entry points: Home is the
public, unpersonalized "what's happening" page; Feed is the login-gated,
personalized one. Both are wired at the project root in config/urls.py
(alongside the pre-existing `home` route), not under this app's own
`news:` namespace. SearchView is wired the same way.
"""
from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.entitlements import user_can
from apps.behavior.services import attach_saved_state, get_followed_keys, mark_read
from apps.catalog.models import Article, ContentTopic, Entity, PersonEntity, Source, TaxonomyTopic, TrendReport, UserRanking, YoutubeVideo
from apps.catalog.services import (
    attach_topics, get_chunks, get_enrichment, get_entities, get_entity_mentions, get_entity_timeline,
    get_full_story, get_hot_clusters, get_person_own_content, get_related_entities,
    get_related_items, get_trending, get_user_visibility_source_keys, resolve_narrative_citations,
)
from apps.news.search import semantic_search
from apps.onboarding.models import UserSourceSubscription
from django.core.paginator import Paginator
from django.http import Http404


class ArticleListView(LoginRequiredMixin, ListView):
    model = Article
    template_name = "news/article_list.html"
    context_object_name = "articles"
    paginate_by = 9

    def get_queryset(self):
        # M10 — visibility='user' sources are private to their subscriber(s)
        # (see apps.catalog.services.get_user_visibility_source_keys); this
        # public/generic browsing page never shows them, subscribed or not.
        qs = Article.objects.exclude(source__in=get_user_visibility_source_keys())
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

        # Cross-source Related (M8): cluster membership first, same-source
        # query as a fallback for items not yet clustered (not everything
        # is — clustering runs on a schedule, not synchronously at scrape time).
        related = get_related_items("article", self.object.pk, limit=4)
        if not related:
            related = list(
                Article.objects.filter(source=self.object.source)
                .exclude(pk=self.object.pk)
                .order_by("-published_at")[:4]
            )
        attach_saved_state(self.request.user, related)
        attach_topics(related)
        ctx["related"] = related

        attach_topics([self.object])
        ctx["topics"] = self.object.topics
        enrichment = get_enrichment("article", self.object.pk)
        ctx["enrichment"] = enrichment
        ctx["entities"] = get_entities("article", self.object.pk)
        ctx["followed_topics"] = get_followed_keys(self.request.user, "topic")
        ctx["followed_entities"] = get_followed_keys(self.request.user, "entity")

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


# M12 — must match run_pipeline.py's LONG_VIDEO_THRESHOLD_SECONDS exactly.
# Duplicated (not imported) because the pipeline (SQLAlchemy) and this app
# (Django) are two separate processes/venvs with no shared import path —
# same convention as DjangoUser's plan-expiry mirror in
# app/database/models/django_readmodels.py.
LONG_VIDEO_THRESHOLD_SECONDS = 1200


class VideoDetailView(LoginRequiredMixin, DetailView):
    model = YoutubeVideo
    template_name = "news/video_detail.html"
    context_object_name = "video"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["reasoning"] = _recommendation_reasoning(self.request.user, "youtube_video", self.object.pk)

        # M12 — chaptered/deep summaries. Chunking runs for EVERY qualifying
        # video regardless of viewer plan (Architecture Principle 1); only
        # this UI section is gated. Non-Pro sees a 200-OK upsell, not a 403
        # (same precedent as TrendReportView above).
        ctx["is_long_video"] = bool(
            self.object.duration_seconds and self.object.duration_seconds >= LONG_VIDEO_THRESHOLD_SECONDS
        )
        ctx["can_view_chapters"] = user_can(self.request.user, "deep_video_summaries")
        ctx["chunks"] = (
            get_chunks("youtube_video", self.object.pk)
            if ctx["is_long_video"] and ctx["can_view_chapters"]
            else []
        )

        # Cross-source Related (M8) — VideoDetailView had NO related-content
        # logic before this; cluster membership only (no same-source
        # fallback query existed here previously, so [] is an honest empty
        # state rather than inventing a new same-channel query unasked-for).
        related = get_related_items("youtube_video", self.object.pk, limit=4)
        attach_saved_state(self.request.user, related)
        attach_topics(related)
        ctx["related"] = related

        attach_topics([self.object])
        ctx["topics"] = self.object.topics
        enrichment = get_enrichment("youtube_video", self.object.pk)
        ctx["enrichment"] = enrichment
        ctx["entities"] = get_entities("youtube_video", self.object.pk)
        ctx["followed_topics"] = get_followed_keys(self.request.user, "topic")
        ctx["followed_entities"] = get_followed_keys(self.request.user, "entity")

        mark_read(self.request.user, "youtube_video", self.object.pk)
        return ctx


def _recommendation_reasoning(user, content_type, content_id):
    """RankingService's templated explanation for this user+item, if a ranking exists — not synthesized here."""
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
        # M10 — visibility='user' sources are private to their subscriber(s);
        # the public Home page never shows them (see FeedView for the
        # personalized path where a subscriber DOES see their own subscriptions).
        articles = Article.objects.exclude(source__in=get_user_visibility_source_keys())
        videos = YoutubeVideo.objects.all()

        query = self.request.GET.get("q", "").strip()
        source = self.request.GET.get("source", "").strip()
        category = self.request.GET.get("category", "").strip()
        topic = self.request.GET.get("topic", "").strip()
        date_from = self.request.GET.get("from", "").strip()

        if source:
            articles = articles.filter(source=source)
            videos = videos if source == "youtube" else videos.none()
        if category:
            source_keys = list(Source.objects.filter(category=category).values_list("key", flat=True))
            articles = articles.filter(source__in=source_keys)
            videos = videos if category == "media" else videos.none()
        if topic:
            # Same two-step ID-lookup shape as the category filter above —
            # ContentTopic is keyed by (content_type, content_id), so resolve
            # matching ids first, then filter each queryset by pk__in.
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

        combined = list(articles) + list(videos)
        combined.sort(key=lambda item: item.published_at, reverse=True)
        self._all_items = combined
        return combined

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        featured = [item for item in self._all_items[:12] if getattr(item, "image_url", None) or hasattr(item, "thumbnail_url")][:3]
        # attach_saved_state/attach_topics are safe here even though
        # `featured` isn't the paginated page — it's already a small fixed
        # slice ([:12] then [:3]), not the full unpaginated result set.
        attach_saved_state(self.request.user, featured)
        attach_topics(featured)
        attach_saved_state(self.request.user, ctx["items"])
        attach_topics(ctx["items"])
        ctx.update({
            "q": self.request.GET.get("q", "").strip(),
            "active_source": self.request.GET.get("source", "").strip(),
            "active_category": self.request.GET.get("category", "").strip(),
            "active_topic": self.request.GET.get("topic", "").strip(),
            "date_from": self.request.GET.get("from", "").strip(),
            "sources": Source.objects.filter(is_active=True).order_by("name"),
            "categories": Source.CATEGORY_LABELS.items(),
            "topics": TaxonomyTopic.objects.filter(is_active=True).order_by("sort_order"),
            "featured": featured,
            "trending": get_trending(),
            "hot_clusters": get_hot_clusters(),
        })
        return ctx


class FeedView(LoginRequiredMixin, ListView):
    """
    Personalized — reads the persisted output of RankingService's two-stage
    ranker (catalog.UserRanking, written by app/tasks/ranking_tasks.py on
    its own schedule — M9, no LLM involved). Django never ranks anything
    itself; it only reads what the pipeline already computed.

    Fallback for users with no ranking yet (brand new, before the scheduled
    ranking task has fired even once): plain date-ordered content with
    their own exclusions applied — an honest empty state, not fake
    personalization.
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

        # M10 — visibility='user' sources are private to their subscriber(s):
        # hide every one EXCEPT this user's own subscriptions (unlike
        # HomeView/ArticleListView, which hide all of them unconditionally).
        user_source_keys = get_user_visibility_source_keys()
        subscribed_keys = set(
            UserSourceSubscription.objects.filter(profile=profile).values_list("source__key", flat=True)
        )
        hidden_user_sources = user_source_keys - subscribed_keys

        articles = Article.objects.exclude(source__in=excluded_all).exclude(source__in=hidden_user_sources)
        videos = YoutubeVideo.objects.all() if "media" not in excluded_categories and "youtube" not in excluded_all else YoutubeVideo.objects.none()
        combined = list(articles) + list(videos)
        combined.sort(key=lambda item: item.published_at, reverse=True)
        return combined

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_ranking"] = self._has_ranking
        attach_saved_state(self.request.user, ctx["items"])
        attach_topics(ctx["items"])
        return ctx


class PeopleListView(LoginRequiredMixin, ListView):
    """
    Browse followable people (M10) — Entity rows with entity_type='person'.
    Following itself needs no new schema (UserFollow(target_type="entity"),
    already built in M9) — this page exists so a person is discoverable/
    searchable at all, since entity chips on article/video detail pages
    only ever surface a person already mentioned in whatever content
    you're currently reading.
    """

    model = Entity
    template_name = "news/people_list.html"
    context_object_name = "people"
    paginate_by = 24

    def get_queryset(self):
        qs = Entity.objects.filter(entity_type="person").order_by("name")
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(name__icontains=query)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "").strip()
        ctx["followed_entities"] = get_followed_keys(self.request.user, "entity")
        return ctx


class EntityDetailView(LoginRequiredMixin, DetailView):
    """
    General entity page (M11 — generalizes M10's person-only PersonDetailView,
    since Entity covers company/model/person/technology and every one of them
    can have a mention timeline/related-entities page, not just people).
    Registered at the project root (/entity/<pk>/, config/urls.py) alongside
    home/feed/search — a first-class surface, not a sub-page of News browsing.

    Always shows: mention timeline sparkline + dated mention list (M11) and
    related entities (M11, co-occurrence). Only for entity_type='person'
    ALSO shows their own scraped output (get_person_own_content, M10) —
    corpus mentions rarely include a person's own writing about themselves,
    so that section stays person-specific, not folded into "mentions".
    """

    model = Entity
    template_name = "news/entity_detail.html"
    context_object_name = "entity"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        entity = self.object

        mentions = get_entity_mentions(entity.id, limit=12)
        attach_saved_state(self.request.user, mentions)
        attach_topics(mentions)
        ctx["mentions"] = mentions
        ctx["timeline"] = get_entity_timeline(entity.id)
        ctx["related_entities"] = get_related_entities(entity.id)
        ctx["followed_entities"] = get_followed_keys(self.request.user, "entity")

        if entity.entity_type == "person":
            own_content = get_person_own_content(entity.id, limit=12)
            attach_saved_state(self.request.user, own_content)
            attach_topics(own_content)
            ctx["own_content"] = own_content
            ctx["footprints"] = PersonEntity.objects.filter(entity_id=entity.id).select_related("source")

        return ctx


class SearchView(TemplateView):
    """
    Public, not personalized (matches Home's access level) — a query box
    over semantic_search() (M9). Plain TemplateView + manual Paginator
    rather than ListView, since semantic_search() returns an already-built
    plain list, not a queryset (same "Paginator works fine over a plain
    list" pattern HomeView/FeedView already established for mixed
    Article+YoutubeVideo result sets).
    """

    template_name = "search.html"
    paginate_by = 12

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        ctx["q"] = query

        if query:
            results, used_semantic = semantic_search(query, limit=60)
            ctx["used_semantic"] = used_semantic
        else:
            results, ctx["used_semantic"] = [], True

        paginator = Paginator(results, self.paginate_by)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        ctx["page_obj"] = page_obj
        ctx["items"] = list(page_obj.object_list)
        ctx["is_paginated"] = page_obj.has_other_pages()

        attach_saved_state(self.request.user, ctx["items"])
        attach_topics(ctx["items"])
        return ctx


class TrendReportView(LoginRequiredMixin, TemplateView):
    """
    Weekly grounded trend narrative (M11, Pro) — /insights/, project root
    alongside Home/Feed/Search/Entity. TrendReport auto-publishes
    immediately after generation (see app.agents.trend_narrative_agent —
    no draft/review gate exists anywhere in this codebase, and none is
    introduced here; the safety net is mechanical citation-grounding at
    generation time). Non-Pro sees a 200-OK upsell state, not a 403 — kept
    discoverable, matching this codebase's one other partial-gate precedent
    (apps.onboarding.source_submission's cap message) rather than hiding
    the page entirely. This is the first full-PAGE Pro gate here.
    """

    template_name = "news/trend_report.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_view"] = user_can(self.request.user, "trend_narrative")
        if ctx["can_view"]:
            report = TrendReport.objects.order_by("-week_start_date").first()
            ctx["report"] = report
            ctx["claims"] = resolve_narrative_citations(report.narrative) if report else []
        return ctx


class StoryClusterView(LoginRequiredMixin, TemplateView):
    """
    One story, all sources (M11, Nice-to-have) — keyed by a content ITEM,
    never a cluster id (see get_full_story's docstring: cluster identity
    churns between pipeline runs). 404s if the item doesn't exist; renders
    an honest "not currently grouped with anything else" state if it exists
    but isn't (or is no longer) clustered, rather than pretending a lone
    item is a multi-source story.
    """

    template_name = "news/story_cluster.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        content_type = self.kwargs["content_type"]
        content_id = self.kwargs["content_id"]
        if content_type not in ("article", "youtube_video"):
            raise Http404("Unknown content type")

        model = Article if content_type == "article" else YoutubeVideo
        anchor = model.objects.filter(pk=content_id).first()
        if anchor is None:
            raise Http404("Item not found")

        members = get_full_story(content_type, content_id)
        attach_saved_state(self.request.user, members)
        attach_topics(members)
        ctx["anchor"] = anchor
        ctx["members"] = members
        return ctx
