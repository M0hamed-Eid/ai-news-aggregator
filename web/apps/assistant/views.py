"""
POST /assistant/message/ — {question, scope?, content_type?, content_id?,
topic_slug?, style?, conversation_id?} -> {answer, citations[], grounded,
suggestions[], conversation_id}. Non-streaming (Phase B/C) — the no-JS /
Render-fallback path, and the one every browser can always fall back to.

POST /assistant/stream/ — same request shape, returns a text/event-stream
response (Phase D): "data: {...}\\n\\n" frames of {"type": "token", "text"}
while generating, then one final {"type": "done", ...same shape as above}.
Retrieval for BOTH views crosses to the pipeline via the same Celery
mechanism; only generation differs (blocking Celery call vs. a direct Groq
stream — see apps.assistant.llm_client's module docstring for why).

Validation + gating (CSRF kept, check_rate_limit, a FollowToggleView-style
boolean-entitlement + numeric-cap gate) is shared by both views via the
helpers below — mirrors apps.behavior.views' JSON-endpoint conventions.
"""
import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views import View

from apps.accounts.entitlements import user_can
from apps.behavior.ratelimit import check_rate_limit

from . import llm_client
from .models import ChatConversation
from .rag_client import ask, retrieve
from .services import get_history, get_or_create_conversation, record_turn

logger = logging.getLogger(__name__)

VALID_SCOPES = {"article", "video", "topic", "kb"}
VALID_CONTENT_TYPES = {"article", "youtube_video"}
VALID_STYLES = {"beginner", "technical", "concise"}
MAX_QUESTION_CHARS = 1000

# Burst limiter — generous enough for a real back-and-forth conversation,
# tight enough to stop a scripted hammering of the (costly) Groq call.
RATE_LIMIT_PER_MINUTE = 12

# M14 — Free tier gets real access with a daily cap; Pro is unlimited.
# Mirrors FollowToggleView/FREE_FOLLOW_LIMIT's exact boolean-entitlement +
# numeric-cap shape (apps.behavior.views), reusing check_rate_limit as the
# daily counter (same non-atomic-soft-limit tradeoff already accepted there).
FREE_DAILY_MESSAGE_LIMIT = 20

_NO_RESULTS_MESSAGE = (
    "I couldn't find anything in the knowledge base about that. "
    "Try rephrasing, or ask about a specific article or video you're viewing."
)


def _parse_message_payload(request):
    """Returns (fields_dict, None) on success or (None, JsonResponse) on a
    validation failure — shared by AssistantMessageView and AssistantStreamView
    so the two request shapes can never silently drift apart."""
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "invalid JSON"}, status=400)

    question = (payload.get("question") or "").strip()
    if not question:
        return None, JsonResponse({"error": "question is required"}, status=400)
    if len(question) > MAX_QUESTION_CHARS:
        return None, JsonResponse({"error": f"question must be under {MAX_QUESTION_CHARS} characters"}, status=400)

    scope = payload.get("scope") or "kb"
    if scope not in VALID_SCOPES:
        return None, JsonResponse({"error": "invalid scope"}, status=400)

    content_type = payload.get("content_type")
    content_id = payload.get("content_id")
    if scope in ("article", "video"):
        if content_type not in VALID_CONTENT_TYPES or not isinstance(content_id, int):
            return None, JsonResponse({"error": "content_type/content_id required for this scope"}, status=400)
    else:
        content_type, content_id = None, None

    topic_slug = payload.get("topic_slug") if scope == "topic" else None
    if scope == "topic" and not topic_slug:
        return None, JsonResponse({"error": "topic_slug required for topic scope"}, status=400)

    style = payload.get("style")
    if style not in VALID_STYLES:
        style = None

    conversation_id = payload.get("conversation_id")
    if conversation_id is not None and not isinstance(conversation_id, int):
        return None, JsonResponse({"error": "conversation_id must be an integer"}, status=400)

    return {
        "question": question, "scope": scope, "content_type": content_type,
        "content_id": content_id, "topic_slug": topic_slug, "style": style,
        "conversation_id": conversation_id,
    }, None


def _check_gates(user):
    """Returns a JsonResponse to short-circuit with, or None if the request may proceed."""
    if not check_rate_limit(f"ratelimit:chat:{user.id}", RATE_LIMIT_PER_MINUTE, 60):
        return JsonResponse({
            "error": "You're asking questions faster than I can answer — please wait a moment and try again.",
        }, status=429)

    if not user_can(user, "ai_assistant_unlimited"):
        quota_key = f"chat:quota:{user.id}:{timezone.now():%Y%m%d}"
        if not check_rate_limit(quota_key, FREE_DAILY_MESSAGE_LIMIT, 86400):
            return JsonResponse({
                "error": f"Free accounts get {FREE_DAILY_MESSAGE_LIMIT} assistant messages a day — upgrade to Pro for unlimited.",
                "upsell": True,
            }, status=403)
    return None


class AssistantMessageView(LoginRequiredMixin, View):

    def post(self, request, *args, **kwargs):
        fields, error = _parse_message_payload(request)
        if error is not None:
            return error

        gate_error = _check_gates(request.user)
        if gate_error is not None:
            return gate_error

        conversation = get_or_create_conversation(
            request.user, fields["conversation_id"], scope=fields["scope"], content_type=fields["content_type"],
            content_id=fields["content_id"], topic_slug=fields["topic_slug"], first_question=fields["question"],
        )
        if conversation is None:
            return JsonResponse({"error": "conversation not found"}, status=404)
        history = get_history(conversation)

        try:
            result = ask(
                fields["question"], user_id=request.user.id, scope=fields["scope"],
                content_type=fields["content_type"], content_id=fields["content_id"],
                topic_slug=fields["topic_slug"], style=fields["style"], history=history,
            )
        except Exception as exc:
            logger.warning("assistant: rag_answer_task failed/timed out — %s", exc)
            return JsonResponse({
                "error": "The assistant is temporarily unavailable. Please try again shortly.",
            }, status=503)

        record_turn(conversation, fields["question"], result)
        result["conversation_id"] = conversation.id
        return JsonResponse(result)


class AssistantStreamView(LoginRequiredMixin, View):
    """
    POST /assistant/stream/ — SSE. Retrieval happens the SAME way as the
    non-streaming view (a blocking Celery call to rag_retrieve_task — it's
    fast, and there's nothing useful to stream during it); only the Groq
    generation call itself streams, directly from this Django process (see
    apps.assistant.llm_client). All validation/gating/persistence is IDENTICAL
    to AssistantMessageView, factored into the shared helpers above so the
    two paths can never answer the same request differently.
    """

    def post(self, request, *args, **kwargs):
        fields, error = _parse_message_payload(request)
        if error is not None:
            return error

        gate_error = _check_gates(request.user)
        if gate_error is not None:
            return gate_error

        if not llm_client.is_configured():
            return JsonResponse({"error": "streaming is not configured on this server"}, status=503)

        conversation = get_or_create_conversation(
            request.user, fields["conversation_id"], scope=fields["scope"], content_type=fields["content_type"],
            content_id=fields["content_id"], topic_slug=fields["topic_slug"], first_question=fields["question"],
        )
        if conversation is None:
            return JsonResponse({"error": "conversation not found"}, status=404)
        history = get_history(conversation)
        question = fields["question"]

        def sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        def event_stream():
            try:
                payload = retrieve(
                    question, user_id=request.user.id, scope=fields["scope"],
                    content_type=fields["content_type"], content_id=fields["content_id"],
                    topic_slug=fields["topic_slug"], style=fields["style"], history=history,
                )
            except Exception as exc:
                logger.warning("assistant stream: rag_retrieve_task failed/timed out — %s", exc)
                yield sse({"type": "error", "error": "The assistant is temporarily unavailable. Please try again shortly."})
                return

            if not payload.get("has_results"):
                result = {"answer": _NO_RESULTS_MESSAGE, "citations": [], "grounded": False, "suggestions": []}
                record_turn(conversation, question, result)
                yield sse({"type": "done", **result, "conversation_id": conversation.id})
                return

            full_text = ""
            try:
                for delta in llm_client.stream_completion(payload["system_prompt"], payload["question"]):
                    full_text += delta
                    yield sse({"type": "token", "text": delta})
            except Exception:
                logger.exception("assistant stream: Groq streaming call failed")
                yield sse({"type": "error", "error": "The assistant is temporarily unavailable. Please try again shortly."})
                return

            cleaned, suggestions = llm_client.extract_suggestions(full_text)
            cleaned, citations = llm_client.resolve_citations(cleaned, payload["handle_to_citation"])
            result = {"answer": cleaned, "citations": citations, "grounded": len(citations) > 0, "suggestions": suggestions}
            record_turn(conversation, question, result)
            yield sse({"type": "done", **result, "conversation_id": conversation.id})

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # reverse-proxy hint: don't buffer this response
        return response


class ConversationHistoryView(LoginRequiredMixin, View):
    """GET /assistant/conversations/<id>/ — re-renders a thread's messages +
    citations on reopen (e.g. the panel was closed then reopened)."""

    def get(self, request, conversation_id, *args, **kwargs):
        conversation = ChatConversation.objects.filter(id=conversation_id, user=request.user).first()
        if conversation is None:
            return JsonResponse({"error": "conversation not found"}, status=404)

        messages = [
            {
                "role": m.role,
                "content": m.content,
                "citations": m.citations,
                "grounded": m.grounded,
                "suggestions": m.suggestions,
            }
            for m in conversation.messages.all()
        ]
        return JsonResponse({
            "conversation_id": conversation.id,
            "scope_type": conversation.scope_type,
            "scope_content_type": conversation.scope_content_type,
            "scope_content_id": conversation.scope_content_id,
            "messages": messages,
        })
