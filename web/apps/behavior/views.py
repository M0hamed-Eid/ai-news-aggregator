import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.entitlements import user_can
from apps.catalog.models import DigestClickToken

from .models import CONTENT_TYPE_CHOICES, SavedItem, UserEvent, UserFollow
from .ratelimit import check_rate_limit, is_first_party

VALID_CONTENT_TYPES = {code for code, _ in CONTENT_TYPE_CHOICES}
VALID_EVENT_TYPES = {code for code, _ in UserEvent.EVENT_TYPE_CHOICES}
VALID_FOLLOW_TARGET_TYPES = {code for code, _ in UserFollow.TARGET_TYPE_CHOICES}
MAX_EVENTS_PER_BATCH = 50
RATE_LIMIT_PER_MINUTE = 60
# M13 — found via audit: promised in docs/ROADMAP.md's Free/Pro table since
# before M9 shipped follow/unfollow, never actually enforced until now.
# Mirrors FREE_CUSTOM_SOURCE_LIMIT's exact pattern (apps.onboarding.source_submission).
FREE_FOLLOW_LIMIT = 20


@method_decorator(csrf_exempt, name="dispatch")
class EventIngestView(View):
    """
    POST /behavior/events/ — {"events": [{event_type, content_type?, content_id?, value?}, ...]}

    ONE endpoint for both batched impressions (IntersectionObserver, many
    items per call) and single-event beacons (dwell on visibilitychange) —
    a single-item batch through the same path, rather than two separate
    mechanisms, per docs/ROADMAP.md M7's "batched impressions; single-event
    beacons" requirement.

    CSRF-exempt: navigator.sendBeacon sends an opaque Blob body, so a CSRF
    token can't travel with it regardless of transport. "First-party only"
    is enforced via Origin/Referer host-matching instead (see ratelimit.py).
    """

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication required"}, status=403)
        if not is_first_party(request):
            return JsonResponse({"error": "cross-site requests not allowed"}, status=403)
        if not check_rate_limit(f"ratelimit:events:{request.user.id}", RATE_LIMIT_PER_MINUTE, 60):
            return JsonResponse({"error": "rate limit exceeded"}, status=429)

        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        events = payload.get("events")
        if not isinstance(events, list) or not events:
            return JsonResponse({"error": "events must be a non-empty array"}, status=400)

        rows = []
        for event in events[:MAX_EVENTS_PER_BATCH]:
            if not isinstance(event, dict):
                continue
            event_type = event.get("event_type")
            if event_type not in VALID_EVENT_TYPES:
                continue
            content_type = event.get("content_type")
            if content_type is not None and content_type not in VALID_CONTENT_TYPES:
                continue
            content_id = event.get("content_id")
            value = event.get("value")
            rows.append(UserEvent(
                user=request.user,
                event_type=event_type,
                content_type=content_type,
                content_id=content_id if isinstance(content_id, int) else None,
                value=value if isinstance(value, (int, float)) else None,
            ))

        if not rows:
            return JsonResponse({"error": "no valid events"}, status=400)

        UserEvent.objects.bulk_create(rows)
        return JsonResponse({"accepted": len(rows)}, status=201)


class _ToggleView(LoginRequiredMixin, View):
    """Shared body for the Save/Hide toggle endpoints — same request/response shape, different field."""

    field_name: str = None
    timestamp_field: str = None
    event_type: str = None

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        content_type = payload.get("content_type")
        content_id = payload.get("content_id")
        if content_type not in VALID_CONTENT_TYPES or not isinstance(content_id, int):
            return JsonResponse({"error": "content_type/content_id required"}, status=400)

        item, _ = SavedItem.objects.get_or_create(
            user=request.user, content_type=content_type, content_id=content_id,
        )
        new_value = not getattr(item, self.field_name)
        setattr(item, self.field_name, new_value)
        setattr(item, self.timestamp_field, timezone.now() if new_value else None)
        item.save(update_fields=[self.field_name, self.timestamp_field, "updated_at"])

        if new_value:
            UserEvent.objects.create(
                user=request.user, event_type=self.event_type,
                content_type=content_type, content_id=content_id,
            )

        return JsonResponse({self.field_name: new_value})


class SaveToggleView(_ToggleView):
    field_name = "is_saved"
    timestamp_field = "saved_at"
    event_type = "save"


class HideToggleView(_ToggleView):
    field_name = "is_hidden"
    timestamp_field = "hidden_at"
    event_type = "hide"


class FollowToggleView(LoginRequiredMixin, View):
    """
    POST /behavior/follow/ — {"target_type": "entity"|"topic"|"source", "target_key": "..."}

    Toggles a UserFollow row and returns {"following": bool} — same
    request/response shape as Save/Hide (_ToggleView above), but keyed by
    (target_type, target_key) instead of (content_type, content_id) since
    follow targets are pipeline-owned lookup rows (entities/topics/sources),
    not polymorphic content items, so a plain delete-or-create toggle is
    simpler here than _ToggleView's boolean-field-on-a-state-row shape.
    """

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        target_type = payload.get("target_type")
        target_key = payload.get("target_key")
        if target_type not in VALID_FOLLOW_TARGET_TYPES or not target_key:
            return JsonResponse({"error": "target_type/target_key required"}, status=400)
        target_key = str(target_key)[:200]

        deleted, _ = UserFollow.objects.filter(
            user=request.user, target_type=target_type, target_key=target_key,
        ).delete()
        if deleted:
            return JsonResponse({"following": False})

        if not user_can(request.user, "unlimited_follows"):
            current_count = UserFollow.objects.filter(user=request.user).count()
            if current_count >= FREE_FOLLOW_LIMIT:
                return JsonResponse({
                    "error": f"Free accounts can follow up to {FREE_FOLLOW_LIMIT} — upgrade to Pro for unlimited.",
                }, status=403)

        UserFollow.objects.create(user=request.user, target_type=target_type, target_key=target_key)
        return JsonResponse({"following": True})


class DigestRedirectView(View):
    """
    GET /r/<token>/ — clicked from a digest email, so there is deliberately
    NO LoginRequiredMixin here: mail clients never carry an active Django
    session/cookie. Looks the token up via the read-only pipeline mirror,
    logs a digest_click UserEvent attributed to the token's user_id, then
    redirects to the REAL content URL resolved from apps.catalog (never
    trusting an embedded URL).
    """

    def get(self, request, token, *args, **kwargs):
        click_token = DigestClickToken.objects.filter(token=token).first()
        if click_token is None:
            return redirect("/")

        content_object = click_token.content_object
        if content_object is None:
            return redirect("/")

        UserEvent.objects.create(
            user_id=click_token.user_id,
            event_type="digest_click",
            content_type=click_token.content_type,
            content_id=click_token.content_id,
        )

        target_url = getattr(content_object, "watch_url", None) or content_object.url
        return redirect(target_url)
