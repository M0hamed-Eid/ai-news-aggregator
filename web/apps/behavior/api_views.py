"""
JSON API for real follow/unfollow (M15 Phase 5 — see
.claude/plans/effervescent-petting-nebula.md). apps.behavior's other real
endpoints (SaveToggleView/HideToggleView at /behavior/save/ and
/behavior/hide/, EventIngestView, DigestRedirectView) were already clean
JSON/redirect views from earlier milestones and stay exactly where they
are — this module exists only because follow/unfollow's read side
(GET /api/news/entities/<id>/, GET /api/news/people/) already returns real
isFollowed state, but the write side (POST /behavior/follow/,
apps.behavior.views.FollowToggleView) had ZERO frontend callers: store.ts's
toggleFollowEntity/toggleFollowTopic were local-only Zustand state with no
server round-trip at all (confirmed live during the M15 Phase 5 audit).
"""
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from apps.catalog.models import TaxonomyTopic

from .services import get_followed_keys, toggle_follow


def _parse_json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "invalid JSON"}, status=400)


class FollowsStateAPIView(LoginRequiredMixin, View):
    """GET /api/behavior/follows/ — real follow state for store.ts's
    followedEntities/followedTopics Sets, seeded once on app load
    (alongside GET /api/session/). Entity ids are returned as plain
    strings (matching EntityProfile.id/serialize_entity_summary's "id"
    field). Topic names, NOT slugs, are returned -- TopicTag throughout
    this frontend is a display-name union (see frontend/src/lib/types.ts),
    never a TaxonomyTopic slug, so UserFollow's stored slugs are resolved
    back to names here to match what the frontend already works with
    everywhere else (TopicBadge, ContentItem.topics)."""

    def get(self, request, *args, **kwargs):
        entity_keys = get_followed_keys(request.user, "entity")
        topic_slugs = get_followed_keys(request.user, "topic")
        topic_names = list(
            TaxonomyTopic.objects.filter(slug__in=topic_slugs).values_list("name", flat=True)
        )
        return JsonResponse({
            "followedEntityIds": sorted(entity_keys),
            "followedTopicNames": sorted(topic_names),
        })


class FollowToggleAPIView(LoginRequiredMixin, View):
    """POST /api/behavior/follow/ — {targetType: 'entity'|'topic', targetKey: string}
    -> {following: bool}. Shares its cap/toggle semantics with the legacy
    apps.behavior.views.FollowToggleView via services.toggle_follow() (see
    that function's own docstring for why the legacy view isn't just
    refactored to call this instead). `targetKey` for target_type='topic'
    is a topic NAME (the frontend's only available identifier) -- resolved
    to the real TaxonomyTopic slug here before storage, so UserFollow.
    target_key stays slug-keyed for topics exactly like every other
    slug-keyed topic reference in this codebase (e.g. _apply_home_filters'
    `taxonomy_topic__slug=topic` filter)."""

    def post(self, request, *args, **kwargs):
        payload, error = _parse_json_body(request)
        if error is not None:
            return error

        target_type = payload.get("targetType")
        target_key = payload.get("targetKey")
        if not target_key:
            return JsonResponse({"error": "targetKey is required"}, status=400)

        if target_type == "topic":
            topic = TaxonomyTopic.objects.filter(name=target_key).first()
            if topic is None:
                return JsonResponse({"error": "unknown topic"}, status=404)
            target_key = topic.slug
        elif target_type != "entity":
            return JsonResponse({"error": "targetType must be 'entity' or 'topic'"}, status=400)

        result = toggle_follow(request.user, target_type, target_key)
        if "error" in result:
            return JsonResponse(result, status=403)
        return JsonResponse(result)
