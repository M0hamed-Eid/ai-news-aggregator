"""
Conversation persistence helpers for the RAG chat assistant (M14 Phase C).

Kept as small module-level functions (not a class) — matches this codebase's
existing service shape for a handful of related helpers with no shared state
(apps.behavior.services' attach_saved_state/get_followed_keys is the closest
Django-side precedent). Retrieval scope is per-MESSAGE, not locked to the
conversation: a conversation's scope_* fields record what it was ANCHORED to
when created (for a future "your conversations" list), but each individual
question can target a different scope (the scope switcher chips let a user
broaden from "this article" to "the whole knowledge base" mid-thread) —
history still carries over regardless of scope changes.
"""
from typing import List, Optional

from .models import ChatConversation, ChatMessage

MAX_HISTORY_MESSAGES = 8  # ~4 turns — enough for condense_query's own 6-message cap to have real context
MAX_TITLE_CHARS = 120


def get_or_create_conversation(
    user,
    conversation_id: Optional[int],
    *,
    scope: str = "kb",
    content_type: Optional[str] = None,
    content_id: Optional[int] = None,
    topic_slug: Optional[str] = None,
    first_question: str = "",
) -> Optional[ChatConversation]:
    """Returns None if conversation_id is given but doesn't belong to this user
    (never silently operate on someone else's conversation)."""
    if conversation_id is not None:
        return ChatConversation.objects.filter(id=conversation_id, user=user).first()

    scope_type = "document" if scope in ("article", "video") else scope
    return ChatConversation.objects.create(
        user=user,
        title=(first_question or "")[:MAX_TITLE_CHARS] or None,
        scope_type=scope_type,
        scope_content_type=content_type if scope_type == "document" else None,
        scope_content_id=content_id if scope_type == "document" else None,
        scope_topic_slug=topic_slug if scope_type == "topic" else None,
    )


def get_history(conversation: ChatConversation, max_messages: int = MAX_HISTORY_MESSAGES) -> List[dict]:
    """Oldest first, capped to the most recent `max_messages` — matches the
    shape condense_query() (app/services/rag_service.py) expects."""
    recent = list(conversation.messages.order_by("-created_at")[:max_messages])
    recent.reverse()
    return [{"role": m.role, "content": m.content} for m in recent]


def record_turn(conversation: ChatConversation, question: str, result: dict) -> None:
    ChatMessage.objects.create(conversation=conversation, role="user", content=question)
    ChatMessage.objects.create(
        conversation=conversation,
        role="assistant",
        content=result.get("answer", ""),
        citations=result.get("citations") or [],
        grounded=result.get("grounded"),
        suggestions=result.get("suggestions") or [],
        total_tokens=result.get("total_tokens"),
    )
    conversation.save(update_fields=["last_active_at"])  # auto_now bumps it; messages alone don't touch the parent row
