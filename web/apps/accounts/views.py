from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from apps.catalog.models import DigestLog
from apps.onboarding.models import Persona

from .forms import RegisterForm


class RegisterView(CreateView):
    """
    Create an account, log the new user straight in, then send them to
    onboarding — the ONE automatic redirect there, since a brand new user
    has never completed it. If they skip or bail out mid-wizard,
    onboarding_completed stays False and they're never force-redirected
    again; they can reopen it from the nav (see base.html) whenever they like.
    """

    form_class = RegisterForm
    template_name = "registration/register.html"
    success_url = reverse_lazy("onboarding:start")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class ProfileView(LoginRequiredMixin, TemplateView):
    """
    View + edit profile basics (name/bio/persona/digest settings). Persona,
    interests, and source exclusions are managed on their own dedicated pages
    (apps.onboarding) — this page focuses on identity + digest delivery, and
    links out to those for anything list-shaped.
    """

    template_name = "registration/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.request.user.profile
        digest_settings = getattr(profile, "digest_settings", None)

        interests = list(profile.interests.select_related("interest").order_by("-weight"))
        exclusions = list(profile.exclusions.all())
        excluded_categories = {e.value for e in exclusions if e.kind == "category"}
        excluded_sources = {e.value for e in exclusions if e.kind == "source"}

        # "Favorite" categories/sources: derived from this user's own
        # persisted ranking output (app/database/models/user_ranking.py via
        # apps.catalog.models.UserRanking) — real signal, not fabricated.
        from collections import Counter
        rankings = list(self.request.user.rankings.all()[:50])
        source_counter = Counter()
        category_counter = Counter()
        for r in rankings:
            obj = r.content_object
            if obj is None:
                continue
            source = getattr(obj, "source", "youtube")
            source_counter[source] += 1

        context.update({
            "profile": profile,
            "digest_settings": digest_settings,
            "personas": Persona.objects.filter(is_active=True),
            "interests": interests,
            "excluded_categories": excluded_categories,
            "excluded_sources": excluded_sources,
            "digests_received_count": DigestLog.objects.filter(user_id=self.request.user.id).count(),
            "favorite_sources": source_counter.most_common(5),
            "ranking_count": len(rankings),
        })
        return context

    def post(self, request, *args, **kwargs):
        profile = request.user.profile
        user = request.user

        user.first_name = request.POST.get("first_name", "").strip()
        user.save(update_fields=["first_name"])

        profile.bio = request.POST.get("bio", "").strip()
        persona_id = request.POST.get("persona") or None
        profile.persona_id = persona_id
        profile.save(update_fields=["bio", "persona"])

        settings_obj = getattr(profile, "digest_settings", None)
        if settings_obj is not None:
            frequency = request.POST.get("frequency")
            if frequency in dict(settings_obj._meta.get_field("frequency").choices):
                settings_obj.frequency = frequency
            settings_obj.is_paused = bool(request.POST.get("is_paused"))
            settings_obj.save()

        messages.success(request, "Profile updated.")
        return redirect("accounts:profile")
