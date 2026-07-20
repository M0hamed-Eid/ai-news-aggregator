"""
Conversation memory for the RAG chat assistant (M14 Phase C).

Django-owned (touches User) — the pipeline SQLAlchemy side never writes or
reads these tables directly; retrieval/generation crosses to the pipeline via
Celery per-request (see rag_client.py), receiving history as plain dicts, not
by that process reading this table itself.

ChatConversation is one thread, anchored to whatever the user was looking at
when they started it (scope_content_type/scope_content_id use the SAME
polymorphic (content_type, content_id) convention as every pipeline-owned
content table, even though these two columns live in a Django table — kept
consistent on purpose so a conversation's anchor reads the same way
everywhere in this codebase). ChatMessage is APPEND-ONLY, one row per turn —
same discipline as UserEvent (apps.behavior.models) — never updated or
deleted except by a future retention prune, matching that precedent.
"""
from django.conf import settings
from django.db import models

CONTENT_TYPE_CHOICES = [
    ("article", "Article"),
    ("youtube_video", "YouTube video"),
]

SCOPE_TYPE_CHOICES = [
    ("document", "Article or video"),
    ("topic", "Topic"),
    ("kb", "Whole knowledge base"),
]

ROLE_CHOICES = [
    ("user", "User"),
    ("assistant", "Assistant"),
]


class ChatConversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_conversations")
    title = models.CharField(max_length=200, null=True, blank=True, help_text="First question, truncated — set once, never re-derived")

    scope_type = models.CharField(max_length=20, choices=SCOPE_TYPE_CHOICES, default="kb")
    scope_content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, null=True, blank=True)
    scope_content_id = models.BigIntegerField(null=True, blank=True)
    scope_topic_slug = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_conversations"
        ordering = ["-last_active_at"]
        indexes = [models.Index(fields=["user", "-last_active_at"], name="ix_chat_conv_user_active")]

    def __str__(self):
        return f"user_id={self.user_id} conversation#{self.pk} ({self.scope_type})"


class ChatMessage(models.Model):
    conversation = models.ForeignKey(ChatConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    citations = models.JSONField(default=list, blank=True, help_text="Resolved Citation dicts, empty for role='user'")
    grounded = models.BooleanField(null=True, blank=True, help_text="Null for role='user' — grounded only applies to assistant turns")
    suggestions = models.JSONField(default=list, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True, help_text="Groq usage.total_tokens when available — cost telemetry, not always populated")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"], name="ix_chat_msg_conv_created")]

    def __str__(self):
        return f"conversation#{self.conversation_id} {self.role}: {self.content[:50]!r}"
