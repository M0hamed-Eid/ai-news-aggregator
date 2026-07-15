"""
Shared helpers threading M8 content-intelligence data (topics, clusters,
entities, enrichment) into content lists/detail views built by apps.news.
Kept here (not in apps.news) since these models are owned by this app.
"""
from .models import Article, ContentCluster, ContentEnrichment, ContentEntity, ContentTopic, YoutubeVideo


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
