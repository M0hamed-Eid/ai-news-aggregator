"""
Shared helpers threading M8 content-intelligence data (topics, clusters,
entities, enrichment) into content lists/detail views built by apps.news.
Kept here (not in apps.news) since these models are owned by this app.
"""
from collections import Counter

from django.db.models import Max, Q

from .models import Article, ContentChunk, ContentCluster, ContentClusterMember, ContentEnrichment, ContentEntity, ContentTopic, Entity, PersonEntity, Source, TaxonomyTopic, Trend, YoutubeVideo


def _content_type_for(item) -> str:
    return "youtube_video" if hasattr(item, "video_id") else "article"


def attach_topics(items):
    """
    Mutates `items` in place, setting .topics (a list of TaxonomyTopic) on
    each, from ONE bulk query. Call this AFTER pagination has already
    sliced the list down to a single page — same discipline as
    apps.behavior.services.attach_saved_state.
    """
    if not items:
        return items

    keys = [(_content_type_for(item), item.pk) for item in items]
    content_types = {k[0] for k in keys}
    content_ids = {k[1] for k in keys}

    topics_by_key = {}
    rows = (
        ContentTopic.objects.filter(content_type__in=content_types, content_id__in=content_ids)
        .select_related("taxonomy_topic")
    )
    for row in rows:
        topics_by_key.setdefault((row.content_type, row.content_id), []).append(row.taxonomy_topic)

    for item, key in zip(items, keys):
        item.topics = topics_by_key.get(key, [])
    return items


def get_related_items(content_type: str, content_id: int, limit: int = 4):
    """
    Cross-source Related: look up (content_type, content_id)'s cluster and
    return other members (any content_type), most similar first. Returns []
    if the item has no cluster yet (not everything is clustered — callers
    should fall back to the old same-source query in that case).
    """
    from .models import ContentClusterMember

    member = (
        ContentClusterMember.objects.filter(content_type=content_type, content_id=content_id).first()
    )
    if member is None:
        return []

    other_members = (
        ContentClusterMember.objects.filter(cluster_id=member.cluster_id)
        .exclude(content_type=content_type, content_id=content_id)
        .order_by("-similarity_to_centroid")[:limit]
    )

    resolved = []
    for m in other_members:
        model = Article if m.content_type == "article" else YoutubeVideo
        obj = model.objects.filter(pk=m.content_id).first()
        if obj is not None:
            resolved.append(obj)
    return resolved


def get_cluster_member_count(content_type: str, content_id: int) -> int:
    """
    Cheap companion to get_related_items/get_full_story: just the total
    cluster size (including the item itself), for a "Part of a story with
    N related items" banner. Deliberately a lightweight .count() rather
    than resolving every member to a real Article/YoutubeVideo object
    (get_full_story's cost) — callers that only need the number, not the
    objects, should use this instead.
    """
    member = ContentClusterMember.objects.filter(content_type=content_type, content_id=content_id).first()
    if member is None:
        return 0
    return ContentClusterMember.objects.filter(cluster_id=member.cluster_id).count()


def get_enrichment(content_type: str, content_id: int):
    """The ContentEnrichment row for one item, or None if not yet enriched."""
    return ContentEnrichment.objects.filter(content_type=content_type, content_id=content_id).first()


def get_entities(content_type: str, content_id: int):
    """Entities mentioned in one item — a single-item detail-page query, not a bulk-list one."""
    rows = (
        ContentEntity.objects.filter(content_type=content_type, content_id=content_id)
        .select_related("entity")
    )
    return [row.entity for row in rows]


def get_chunks(content_type: str, content_id: int):
    """
    M12 — chaptered chunk rows for one long video, in order. Empty for any
    video below LONG_VIDEO_THRESHOLD_SECONDS or not yet processed by
    run_pipeline.py::run_deep_video_phase. Ordering is already
    (content_type, content_id, chunk_index) via ContentChunk.Meta.ordering.
    """
    return list(ContentChunk.objects.filter(content_type=content_type, content_id=content_id))


def get_user_visibility_source_keys():
    """
    Source.key values with visibility='user' (M10) — these are private to
    their subscriber(s), never publicly browsable. Callers exclude this set
    from public Home/News querysets unconditionally; FeedView's no-ranking
    fallback instead excludes this set MINUS the current user's own
    subscriptions (see apps.news.views.FeedView).
    """
    return set(Source.objects.filter(visibility="user").values_list("key", flat=True))


def _resolve_content(content_type: str, content_id: int):
    model = Article if content_type == "article" else YoutubeVideo
    return model.objects.filter(pk=content_id).first()


def get_person_own_content(entity_id: int, limit: int = 20):
    """
    A followed person's OWN scraped output (M10) — resolved via
    person_entities, not content_entities (a person's own posts/videos
    rarely mention them by name, so mention-matching alone would miss most
    of it; see app.services.ranking_service._followed_person_footprints for
    the same reasoning applied to ranking). YouTube footprints match on
    channel_id (every channel shares the single "youtube" Source row, so
    Source.key can't disambiguate one person's channel); blog/github/
    substack footprints match on their own dedicated Source.key.
    """
    footprints = PersonEntity.objects.filter(entity_id=entity_id).select_related("source")

    items = []
    for fp in footprints:
        if fp.footprint_type == "youtube":
            if fp.external_identifier:
                items.extend(YoutubeVideo.objects.filter(channel_id=fp.external_identifier))
        elif fp.source_id is not None:
            items.extend(Article.objects.filter(source=fp.source.key))

    items.sort(key=lambda i: i.published_at, reverse=True)
    return items[:limit]


def get_entity_mentions(entity_id: int, limit: int = 20):
    """
    Corpus items that MENTION this entity (content_entities reverse lookup) —
    never entity_type-specific internally (was named get_person_mentions in
    M10, before M11 generalized the detail page to any entity). For a
    person specifically, this is the other half of "own output + mentions"
    alongside get_person_own_content.
    """
    rows = ContentEntity.objects.filter(entity_id=entity_id).order_by("-created_at")[: limit * 2]
    resolved = []
    for row in rows:
        obj = _resolve_content(row.content_type, row.content_id)
        if obj is not None:
            resolved.append(obj)
        if len(resolved) >= limit:
            break
    return resolved


def get_entity_timeline(entity_id: int, days: int = 90):
    """Daily mention-count history for this entity's sparkline (M11) — reads
    the same `trends` rows the Home Trending module reads, just filtered to
    one entity (see Trend's own docstring for why there's no second
    "materialized" timeline table)."""
    from datetime import timedelta

    from django.utils import timezone

    cutoff = timezone.now().date() - timedelta(days=days)
    return list(
        Trend.objects.filter(dimension="entity", key=str(entity_id), date__gte=cutoff).order_by("date")
    )


def get_related_entities(entity_id: int, limit: int = 8):
    """
    Entities that co-occur with this one in the same content items most
    often (M11) — Python-side Counter over a bounded recent-mentions fetch,
    same style as get_related_items/get_entity_mentions (never raw SQL for
    this class of service function in this codebase).
    """
    keys = list(
        ContentEntity.objects.filter(entity_id=entity_id)
        .order_by("-created_at")
        .values_list("content_type", "content_id")[:500]
    )
    if not keys:
        return []

    content_types = {k[0] for k in keys}
    content_ids = {k[1] for k in keys}
    co_occurring = (
        ContentEntity.objects.filter(content_type__in=content_types, content_id__in=content_ids)
        .exclude(entity_id=entity_id)
        .values_list("entity_id", flat=True)
    )
    counts = Counter(co_occurring)
    top_ids = [eid for eid, _ in counts.most_common(limit)]
    entities_by_id = {e.id: e for e in Entity.objects.filter(id__in=top_ids)}
    return [entities_by_id[eid] for eid in top_ids if eid in entities_by_id]


def get_hot_clusters(limit: int = 5, hours: int = 48):
    """
    Cluster-size velocity (M11) — computed live, NEVER persisted.
    ContentCluster ids churn between pipeline runs (wholesale rebuilt every
    ~6h, see that model's own docstring), so there's no stable id to track
    "growth" against across days, and ContentClusterMember.created_at
    reflects the last REBUILD time for every member (not when a story
    actually grew) since the whole table is replaced each run — neither can
    be used as a "recently added" signal. The real signal here is:
    clusters with >=2 members whose underlying CONTENT was published
    recently — i.e. multiple sources just covered the same story.
    """
    from datetime import timedelta

    from django.utils import timezone

    cutoff = timezone.now() - timedelta(hours=hours)
    recent_article_ids = set(Article.objects.filter(published_at__gte=cutoff).values_list("id", flat=True))
    recent_video_ids = set(YoutubeVideo.objects.filter(published_at__gte=cutoff).values_list("id", flat=True))
    if not recent_article_ids and not recent_video_ids:
        return []

    members = (
        ContentClusterMember.objects.filter(
            Q(content_type="article", content_id__in=recent_article_ids)
            | Q(content_type="youtube_video", content_id__in=recent_video_ids)
        )
        .values_list("cluster_id", "content_type", "content_id")
    )

    counts = Counter()
    sample_member = {}
    for cluster_id, content_type, content_id in members:
        counts[cluster_id] += 1
        sample_member.setdefault(cluster_id, (content_type, content_id))

    hot_cluster_ids = [cid for cid, count in counts.most_common() if count >= 2][:limit]

    results = []
    for cluster_id in hot_cluster_ids:
        content_type, content_id = sample_member[cluster_id]
        representative = _resolve_content(content_type, content_id)
        if representative is not None:
            results.append({
                "cluster_id": cluster_id,
                "member_count": counts[cluster_id],
                "representative": representative,
                "representative_content_type": content_type,
            })
    return results


def get_trending(limit: int = 8):
    """
    Home Trending module (M11) — today's statistically-trending topics/
    entities (burst detection, see run_pipeline.py::run_trend_computation_phase),
    resolved to display objects with an "Nx normal" badge. Reads the MOST
    RECENT date present in `trends` rather than assuming "today" has already
    been computed — the pipeline only refreshes today's row once it actually
    runs (up to every 6h), so this degrades gracefully instead of flashing
    an empty state right after UTC midnight.
    """
    latest_date = Trend.objects.aggregate(latest=Max("date"))["latest"]
    if latest_date is None:
        return []

    rows = list(Trend.objects.filter(date=latest_date, is_trending=True).order_by("-z_score")[:limit])
    if not rows:
        return []

    topic_slugs = [r.key for r in rows if r.dimension == "topic"]
    entity_ids = [int(r.key) for r in rows if r.dimension == "entity"]
    topics_by_slug = {t.slug: t for t in TaxonomyTopic.objects.filter(slug__in=topic_slugs)}
    entities_by_id = {e.id: e for e in Entity.objects.filter(id__in=entity_ids)}

    results = []
    for row in rows:
        obj = topics_by_slug.get(row.key) if row.dimension == "topic" else entities_by_id.get(int(row.key))
        if obj is None:
            continue
        results.append({
            "dimension": row.dimension,
            "object": obj,
            "mention_count": row.mention_count,
            "multiplier": round(row.mention_count / max(row.baseline_mean, 0.1), 1),
        })
    return results


def get_full_story(content_type: str, content_id: int):
    """
    Full cross-source story view (M11, Nice-to-have) — every real member of
    the same cluster as this content item (including the item itself).
    Keyed by the CONTENT ITEM, never a cluster id — see ContentCluster's
    own docstring: cluster identity churns between pipeline runs (wholesale
    rebuilt every ~6h), so a URL keyed by cluster_id would silently start
    pointing at an unrelated story after the next rebuild.
    """
    member = ContentClusterMember.objects.filter(content_type=content_type, content_id=content_id).first()
    if member is None:
        return []
    all_members = ContentClusterMember.objects.filter(cluster_id=member.cluster_id).order_by("-similarity_to_centroid")
    resolved = []
    for m in all_members:
        obj = _resolve_content(m.content_type, m.content_id)
        if obj is not None:
            resolved.append(obj)
    return resolved


def resolve_narrative_citations(narrative: list):
    """
    For a TrendReport.narrative claim-list (M11), resolve each claim's
    citations to real Article/YoutubeVideo objects for rendering as links.
    Citations were already server-validated at generation time (see
    TrendNarrativeAgent) — this defensive re-check just means the page
    never 500s if underlying content is later deleted; a citation that
    fails to resolve is silently dropped from display, not the whole claim.
    """
    resolved_claims = []
    for claim in narrative or []:
        items = []
        for c in claim.get("citations", []):
            obj = _resolve_content(c.get("content_type"), c.get("content_id"))
            if obj is not None:
                items.append(obj)
        resolved_claims.append({**claim, "citation_items": items})
    return resolved_claims
