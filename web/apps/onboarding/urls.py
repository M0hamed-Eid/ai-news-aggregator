from django.urls import path

from .views import (
    AddSourceView, OnboardingWizardView, PreferencesView, SourcesView, UnsubscribeSourceView,
)

app_name = "onboarding"

urlpatterns = [
    path("", OnboardingWizardView.as_view(), name="start"),
    path("preferences/", PreferencesView.as_view(), name="preferences"),
    path("sources/", SourcesView.as_view(), name="sources"),
    path("sources/add/", AddSourceView.as_view(), name="add_source"),
    path("sources/unsubscribe/<int:source_id>/", UnsubscribeSourceView.as_view(), name="unsubscribe_source"),
]
