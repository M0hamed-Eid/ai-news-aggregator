from django.urls import path

from .api_views import (
    AddSourceAPIView, InterestsAPIView, PersonasAPIView, SourcesAPIView, UnsubscribeSourceAPIView,
    WizardCompleteAPIView, WizardStateAPIView,
)

app_name = "onboarding_api"

urlpatterns = [
    path("personas/", PersonasAPIView.as_view(), name="personas"),
    path("interests/", InterestsAPIView.as_view(), name="interests"),
    path("sources/", SourcesAPIView.as_view(), name="sources"),
    path("sources/add/", AddSourceAPIView.as_view(), name="add_source"),
    path("sources/<int:source_id>/unsubscribe/", UnsubscribeSourceAPIView.as_view(), name="unsubscribe_source"),
    path("wizard/", WizardStateAPIView.as_view(), name="wizard_state"),
    path("wizard/complete/", WizardCompleteAPIView.as_view(), name="wizard_complete"),
]
