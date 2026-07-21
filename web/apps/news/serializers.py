"""
Article/YoutubeVideo -> JSON, matching frontend/src/lib/types.ts's
ArticleItem/VideoItem shape EXACTLY (field names, not just meaning) — this is
the ONE place that mapping is defined, so the Django JSON API
(apps.news.api_views) and the eventual TypeScript consumer can never drift
apart silently.

Two mappings deliberately do NOT do what their name might suggest, found by
checking real dev-DB data before writing this:
  - ArticleItem.category / VideoItem.category is NOT
    ContentEnrichment.content_category (that's a content-FORMAT
    classification — research/opinion/tutorial/announcement/product-launch/
    tooling/other; confirmed via real value counts) — it's Source.category
    (research/open_source/product_model_databases/developer_communities/
    government/funding/media), resolved through the item's `source` key.
    Source.CATEGORY_LABELS' values are already an exact string-for-string
    match with the frontend's ContentCategory union.
  - ArticleItem/VideoItem.topics is typed as a fixed TopicTag union in
    TypeScript, but the REAL taxonomy (27 rows, apps.catalog.models.
    TaxonomyTopic) only partially overlaps that union — several TopicTag
    values ("OpenAI", "Anthropic", ...) are actually company Entities in
    this schema, not topics at all. Since frontend/next.config.ts already
    sets `typescript: { ignoreBuildErrors: true }` (inherited from the Z.ai
    build), nothing enforces that union at runtime — real topic chips are
    serialized as plain taxonomy-topic name strings here, and company
    mentions stay on mentionedEntities/the entity-follow path instead of
    being force-fit into "topics".
"""
from apps.catalog.models import Source

# M12 — must match run_pipeline.py's LONG_VIDEO_THRESHOLD_SECONDS and
# apps.news.views.LONG_VIDEO_THRESHOLD_SECONDS exactly (see that constant's
# own comment for why this is duplicated, not imported, across the three
# separate processes/venvs involved).
LONG_VIDEO_THRESHOLD_SECONDS = 1200


def bulk_source_category_labels(items) -> dict:
    """One query resolving every distinct `source` key on `items` to its
    Source.CATEGORY_LABELS-mapped display label — call once per page/list,
    same "bulk-attach after pagination" discipline as attach_saved_state/
    attach_topics."""
    keys = {item.source for item in items}
    sources = Source.objects.filter(key__in=keys)
    return {s.key: s.category_label for s in sources}


def _content_type_for(item) -> str:
    return "youtube_video" if hasattr(item, "video_id") else "article"


def _content_type_label(content_category: str | None, source_key: str) -> str | None:
    """Best-effort ArticleItem.contentType ('article' | 'release' | 'paper') —
    a soft, optional badge field, not a hard classification. Absent
    enrichment or an unmapped content_category yields None (omitted from the
    dict) rather than a guessed value."""
    if content_category == "product-launch":
        return "release"
    if source_key == "arxiv":
        return "paper"
    if content_category in ("research", "tutorial", "announcement", "opinion", "tooling", "other"):
        return "article"
    return None


def serialize_item(item, *, category_labels: dict, topics_attached: bool = True, entities=None, enrichment=None) -> dict:
    """
    Shared core for both Article and YoutubeVideo — every field name below
    matches frontend/src/lib/types.ts's ArticleItem/VideoItem verbatim.
    Callers are expected to have already run attach_saved_state()/
    attach_topics() (bulk, list-level) on `item`; `entities`/`enrichment` are
    passed in explicitly for single-item detail calls where a per-item
    lookup is fine (see apps.news.api_views' detail endpoints).
    """
    content_type = _content_type_for(item)
    is_video = content_type == "youtube_video"

    mentioned_entities = [
        {"id": str(e.id), "name": e.name, "type": e.entity_type}
        for e in (entities if entities is not None else [])
    ]

    topics = [t.name for t in getattr(item, "topics", [])] if topics_attached else []

    # Type-prefixed, not a bare str(pk): Article and YoutubeVideo have
    # INDEPENDENT auto-increment ids, so a bare numeric string would let an
    # article and a video with the same pk collide in the frontend's
    # flat Set<string>-keyed savedItems/hiddenItems store (Zustand,
    # frontend/src/lib/store.ts) -- confirmed this is exactly the scheme
    # Z.ai's own mock data already used ("feat-1", "v1", ...), just with
    # real ids instead of fake ones.
    data = {
        "id": f"video-{item.pk}" if is_video else f"article-{item.pk}",
        "type": "video" if is_video else "article",
        "title": item.title,
        "summary": item.summary or "",
        "whyItMatters": enrichment.why_it_matters if enrichment else None,
        "author": None if is_video else (item.author or None),
        "source": item.source,
        "sourceLabel": item.channel_name if is_video else item.source_label,
        "url": item.watch_url if is_video else item.url,
        "publishedAt": item.published_at.isoformat(),
        "category": category_labels.get(item.source, item.source),
        "topics": topics,
        "mentionedEntities": mentioned_entities,
        "technicalDepth": enrichment.technical_depth if enrichment else None,
        "recommendedReason": getattr(item, "reasoning", None),
        "rank": getattr(item, "rank", None),
        "isSaved": bool(getattr(item, "is_saved", False)),
        "isRead": bool(getattr(item, "is_read", False)),
        "isHidden": bool(getattr(item, "is_hidden", False)),
    }

    if is_video:
        data.update({
            "channelName": item.channel_name,
            "thumbnailUrl": item.thumbnail_url,
            "videoId": item.video_id,
            "duration": item.duration_seconds or 0,
            "hasTranscript": bool(item.transcript_segments),
        })
    else:
        data.update({
            "imageUrl": item.image_url or None,
            "contentType": _content_type_label(
                enrichment.content_category if enrichment else None, item.source
            ),
        })

    return data


def serialize_list(items) -> list[dict]:
    """
    List-page variant — expects attach_saved_state()/attach_topics() already
    called on `items` (bulk), and bulk-resolves category labels + entity
    mentions itself so callers (HomeFeedAPIView/FeedAPIView/SearchAPIView)
    never need a per-item query in a loop.
    """
    if not items:
        return []

    from apps.catalog.services import get_enrichment

    category_labels = bulk_source_category_labels(items)

    # Entity mentions: one bulk query across the whole page, not N.
    from apps.catalog.models import ContentEntity
    keys = [(_content_type_for(item), item.pk) for item in items]
    content_types = {k[0] for k in keys}
    content_ids = {k[1] for k in keys}
    entities_by_key: dict = {}
    for row in ContentEntity.objects.filter(
        content_type__in=content_types, content_id__in=content_ids
    ).select_related("entity"):
        entities_by_key.setdefault((row.content_type, row.content_id), []).append(row.entity)

    # Enrichment: also bulk, not per-item (get_enrichment() is a single-row
    # helper meant for detail pages — a list page reuses its underlying
    # model directly instead of calling it in a loop).
    from apps.catalog.models import ContentEnrichment
    enrichment_by_key = {
        (row.content_type, row.content_id): row
        for row in ContentEnrichment.objects.filter(
            content_type__in=content_types, content_id__in=content_ids
        )
    }

    result = []
    for item, key in zip(items, keys):
        result.append(serialize_item(
            item,
            category_labels=category_labels,
            entities=entities_by_key.get(key, []),
            enrichment=enrichment_by_key.get(key),
        ))
    return result


def serialize_detail(item, *, request_user) -> dict:
    """Detail-page variant — a single item, so per-item lookups (attach_saved_state/
    attach_topics/get_entities/get_enrichment) are fine here, same cost profile
    as ArticleDetailView/VideoDetailView already accept."""
    from apps.behavior.services import attach_saved_state
    from apps.catalog.services import attach_topics, get_enrichment, get_entities

    attach_saved_state(request_user, [item])
    attach_topics([item])
    category_labels = bulk_source_category_labels([item])
    entities = get_entities(_content_type_for(item), item.pk)
    enrichment = get_enrichment(_content_type_for(item), item.pk)
    return serialize_item(item, category_labels=category_labels, entities=entities, enrichment=enrichment)


def serialize_entity_summary(entity, *, followed_keys: set) -> dict:
    """Light shape for list contexts (PeoplePage, an entity's own `related`
    list) — matches only the fields those views actually read
    (frontend/src/lib/types.ts's EntityProfile has more fields, but
    ownOutput/mentions/mentionData are detail-page-only and expensive; a
    partial dict is fine here since nothing enforces the full interface at
    runtime — next.config.ts already sets typescript.ignoreBuildErrors:true)."""
    return {
        "id": str(entity.id),
        "name": entity.name,
        "type": entity.entity_type,
        # Entity (apps.catalog.models) has no bio column at all -- None
        # here is an honest "we don't have this", not a bug to fix.
        "bio": None,
        "isFollowed": str(entity.id) in followed_keys,
    }


def serialize_entity_detail(entity, *, request_user) -> dict:
    """Full EntityProfile shape for GET /api/news/entities/<id>/ — reuses
    apps.catalog.services' EXISTING entity-page helpers (the same ones
    apps.news.views.EntityDetailView already calls for the template
    version), just serialized to JSON instead of rendered."""
    from apps.behavior.services import attach_saved_state, get_followed_keys
    from apps.catalog.services import (
        attach_topics, get_entity_mentions, get_entity_timeline,
        get_person_own_content, get_related_entities,
    )

    followed_keys = get_followed_keys(request_user, "entity")

    own_output = get_person_own_content(entity.id) if entity.entity_type == "person" else []
    mentions = get_entity_mentions(entity.id)
    for bucket in (own_output, mentions):
        attach_saved_state(request_user, bucket)
        attach_topics(bucket)

    related = get_related_entities(entity.id)

    return {
        **serialize_entity_summary(entity, followed_keys=followed_keys),
        "mentionData": [
            {"date": t.date.isoformat(), "count": t.mention_count}
            for t in get_entity_timeline(entity.id)
        ],
        "ownOutput": serialize_list(own_output),
        "mentions": serialize_list(mentions),
        "related": [serialize_entity_summary(e, followed_keys=followed_keys) for e in related],
    }
