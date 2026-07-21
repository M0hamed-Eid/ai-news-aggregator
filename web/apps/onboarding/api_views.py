"""
JSON API for onboarding/preferences/sources (M15 frontend integration).
Reuses save_interests()/save_exclusions() (services.py) and
submit_source()/submit_youtube_source() (source_submission.py) verbatim —
the exact same write-paths the template views (views.py) already call.

The new frontend's onboarding wizard is a client-side multi-step form that
never reloads between steps (unlike the old template wizard, which POSTed
and redirected per step) — so instead of mirroring 3 separate step
endpoints, WizardCompleteAPIView takes the whole wizard's state in one call,
matching how the frontend actually collects it (local component state
across steps, submitted once at the end).
"""
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from apps.catalog.models import Source

from .models import Interest, Persona, UserSourceSubscription
from .services import save_exclusions, save_interests
from .source_submission import submit_source, submit_youtube_source


def _parse_json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "invalid JSON"}, status=400)


def _serialize_interests(profile):
    selected_ids = set(profile.interests.values_list("interest_id", flat=True))
    interests = [
        {"id": i.id, "slug": i.slug, "name": i.name, "category": i.category or "Other"}
        for i in Interest.objects.filter(is_active=True)
    ]
    return interests, sorted(selected_ids)


class PersonasAPIView(LoginRequiredMixin, View):
    """GET /api/onboarding/personas/"""

    def get(self, request, *args, **kwargs):
        personas = [
            {"id": p.id, "slug": p.slug, "name": p.name, "description": p.description}
            for p in Persona.objects.filter(is_active=True)
        ]
        return JsonResponse({"personas": personas, "selectedId": request.user.profile.persona_id})


class InterestsAPIView(LoginRequiredMixin, View):
    """GET/POST /api/onboarding/interests/ — the standalone Preferences page's
    real backing store (NOT the same vocabulary as content topic chips —
    Interest is a curated 15-row list, distinct from the 27-row TaxonomyTopic
    apps.news.serializers uses for article/video topics; see Interest's own
    docstring)."""

    def get(self, request, *args, **kwargs):
        interests, selected_ids = _serialize_interests(request.user.profile)
        return JsonResponse({"interests": interests, "selectedIds": selected_ids})

    def post(self, request, *args, **kwargs):
        payload, error = _parse_json_body(request)
        if error is not None:
            return error
        interest_ids = payload.get("interestIds") or []
        if not isinstance(interest_ids, list):
            return JsonResponse({"error": "interestIds must be a list"}, status=400)
        save_interests(request.user.profile, interest_ids)
        interests, selected_ids = _serialize_interests(request.user.profile)
        return JsonResponse({"interests": interests, "selectedIds": selected_ids})


class SourcesAPIView(LoginRequiredMixin, View):
    """GET/POST /api/onboarding/sources/ — mirrors apps.onboarding.views.SourcesView
    exactly: global (curated) sources with per-user exclusion state, plus this
    user's own submitted sources and subscriptions."""

    def get(self, request, *args, **kwargs):
        profile = request.user.profile
        exclusions = list(profile.exclusions.all())
        excluded_sources = {e.value for e in exclusions if e.kind == "source"}
        excluded_categories = {e.value for e in exclusions if e.kind == "category"}

        sources = Source.objects.filter(is_active=True, visibility="global").order_by("name")
        my_sources = Source.objects.filter(visibility="user", created_by=request.user.id)
        my_subscriptions = UserSourceSubscription.objects.filter(profile=profile).select_related("source")
        subscribed_keys = {s.source.key for s in my_subscriptions}

        return JsonResponse({
            "sources": [
                {
                    "key": s.key, "name": s.name, "category": s.category_label,
                    "isExcluded": s.key in excluded_sources,
                }
                for s in sources
            ],
            "categories": list(Source.CATEGORY_LABELS.values()),
            "excludedCategories": [
                Source.CATEGORY_LABELS.get(c, c) for c in excluded_categories
            ],
            "mySubmissions": [
                {
                    "key": s.key, "name": s.name, "category": s.category_label,
                    "status": "accepted" if s.key in subscribed_keys else "pending",
                }
                for s in my_sources
            ],
        })

    def post(self, request, *args, **kwargs):
        """Body: {excludedSourceKeys: string[], excludedCategoryKeys: string[]}
        (category keys, e.g. "research" — NOT the display label) — replaces
        this user's full exclusion set for both kinds at once, matching the
        template SourcesView's "always fully shown, safe to replace
        wholesale" comment on categories (7 is a small fixed set)."""
        payload, error = _parse_json_body(request)
        if error is not None:
            return error
        profile = request.user.profile
        save_exclusions(profile, "source", payload.get("excludedSourceKeys") or [])
        save_exclusions(profile, "category", payload.get("excludedCategoryKeys") or [])
        return JsonResponse({"ok": True})


class AddSourceAPIView(LoginRequiredMixin, View):
    """POST /api/onboarding/sources/add/ — {sourceType: 'rss'|'youtube',
    feedUrl|channelUrl, name, category} -> runs the SAME AI-relevance gate
    (Celery round-trip) as the template AddSourceView, JSON response instead
    of a redirect+message banner."""

    def post(self, request, *args, **kwargs):
        payload, error = _parse_json_body(request)
        if error is not None:
            return error

        category = payload.get("category") or "developer_communities"
        if payload.get("sourceType") == "youtube":
            result = submit_youtube_source(
                request.user,
                channel_url=payload.get("channelUrl", ""),
                name=payload.get("name", ""),
                category=category,
            )
        else:
            result = submit_source(
                request.user,
                feed_url=payload.get("feedUrl", ""),
                name=payload.get("name", ""),
                category=category,
            )

        return JsonResponse(result, status=200 if result["ok"] else 400)


class UnsubscribeSourceAPIView(LoginRequiredMixin, View):
    """POST /api/onboarding/sources/<int:source_id>/unsubscribe/"""

    def post(self, request, source_id, *args, **kwargs):
        deleted, _ = UserSourceSubscription.objects.filter(
            profile=request.user.profile, source_id=source_id,
        ).delete()
        return JsonResponse({"ok": bool(deleted)})


class WizardStateAPIView(LoginRequiredMixin, View):
    """GET /api/onboarding/wizard/ — everything the 3-step wizard needs in one
    call (personas, interests+selected, sources+excluded, current
    onboarding_completed) since the new frontend never reloads between
    steps, unlike the old per-step template wizard."""

    def get(self, request, *args, **kwargs):
        profile = request.user.profile
        interests, selected_interest_ids = _serialize_interests(profile)
        excluded_sources = {e.value for e in profile.exclusions.filter(kind="source")}

        return JsonResponse({
            "onboardingCompleted": profile.onboarding_completed,
            "personas": [
                {"id": p.id, "slug": p.slug, "name": p.name, "description": p.description}
                for p in Persona.objects.filter(is_active=True)
            ],
            "selectedPersonaId": profile.persona_id,
            "interests": interests,
            "selectedInterestIds": selected_interest_ids,
            "sources": [
                {"key": s.key, "name": s.name, "category": s.category_label}
                for s in Source.objects.filter(is_active=True).order_by("name")
            ],
            "excludedSourceKeys": sorted(excluded_sources),
        })


class WizardCompleteAPIView(LoginRequiredMixin, View):
    """POST /api/onboarding/wizard/complete/ — {personaId?, interestIds?,
    excludedSourceKeys?} -> saves everything the wizard collected in one
    shot and flips onboarding_completed=True, reusing the exact same
    save_interests()/save_exclusions() write-paths as the standalone
    Preferences/Sources pages."""

    def post(self, request, *args, **kwargs):
        payload, error = _parse_json_body(request)
        if error is not None:
            return error

        profile = request.user.profile
        persona_id = payload.get("personaId")
        if persona_id is not None:
            profile.persona_id = persona_id
        profile.onboarding_completed = True
        profile.save(update_fields=["persona", "onboarding_completed"])

        save_interests(profile, payload.get("interestIds") or [])
        save_exclusions(profile, "source", payload.get("excludedSourceKeys") or [])

        return JsonResponse({"ok": True})
