from django.urls import path

from .views import AssistantMessageView, AssistantStreamView, ConversationHistoryView

app_name = "assistant"

urlpatterns = [
    path("message/", AssistantMessageView.as_view(), name="message"),
    path("stream/", AssistantStreamView.as_view(), name="stream"),
    path("conversations/<int:conversation_id>/", ConversationHistoryView.as_view(), name="conversation_history"),
]
