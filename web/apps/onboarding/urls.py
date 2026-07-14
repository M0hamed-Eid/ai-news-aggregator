from django.urls import path

from .views import OnboardingWizardView, PreferencesView, SourcesView

app_name = "onboarding"

urlpatterns = [
    path("", OnboardingWizardView.as_view(), name="start"),
    path("preferences/", PreferencesView.as_view(), name="preferences"),
    path("sources/", SourcesView.as_view(), name="sources"),
]
