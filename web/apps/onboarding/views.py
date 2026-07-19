# web/apps/onboarding/views.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import TemplateView, View

from apps.catalog.models import Source

from .models import Interest, Persona, UserSourceSubscription
from .services import save_exclusions, save_interests
from .source_submission import submit_source, submit_youtube_source


class PreferencesView(LoginRequiredMixin, TemplateView):
    """Standalone interests-management page — chip UI over the 15 seeded Interests."""

    template_name = "onboarding/preferences.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.request.user.profile
        selected_ids = set(profile.interests.values_list("interest_id", flat=True))

        interests_by_category = {}
        for interest in Interest.objects.filter(is_active=True):
            interests_by_category.setdefault(interest.category or "other", []).append(interest)

        context.update({
            "interests_by_category": interests_by_category,
            "selected_ids": selected_ids,
        })
        return context

    def post(self, request, *args, **kwargs):
        save_interests(request.user.profile, request.POST.getlist("interests"))
        messages.success(request, "Your interests were updated — they'll shape your next feed ranking.")
        return redirect("onboarding:preferences")


class SourcesView(LoginRequiredMixin, TemplateView):
    """
    Source Registry browser + per-user include/exclude toggles. Every active
    Source row (app/database/models/source.py, read via the catalog mirror)
    is shown; toggling writes/deletes UserExclusion(kind="source") rows —
    changes take effect on the NEXT digest/ranking run (ranking is a batch
    process, not something re-computed live per page view — see
    app/services/digest_service.py).
    """

    template_name = "onboarding/sources.html"

    CATEGORY_LABELS = Source.CATEGORY_LABELS

    def _filtered_sources(self, q, category_filter):
        # visibility='global' only (M10) — user-submitted sources are
        # opt-IN via UserSourceSubscription, not opt-out via UserExclusion,
        # so they must never appear in THIS on-by-default checkbox list
        # (a user-source the current user isn't subscribed to would
        # otherwise render as "checked"/included by mistake, since absence
        # of an exclusion row means included for the exclusion model).
        sources = Source.objects.filter(is_active=True, visibility="global")
        if q:
            sources = sources.filter(name__icontains=q)
        if category_filter:
            sources = sources.filter(category=category_filter)
        return sources

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.request.user.profile
        exclusions = list(profile.exclusions.all())
        excluded_sources = {e.value for e in exclusions if e.kind == "source"}
        excluded_categories = {e.value for e in exclusions if e.kind == "category"}

        q = self.request.GET.get("q", "").strip()
        category_filter = self.request.GET.get("category", "")

        # M10 — user-submitted sources: this user's own submissions (any
        # validation outcome, for transparency) and every source they're
        # subscribed to (their own + anyone else's already-registered ones).
        my_sources = Source.objects.filter(visibility="user", created_by=self.request.user.id)
        my_subscriptions = (
            UserSourceSubscription.objects.filter(profile=profile).select_related("source")
        )

        context.update({
            "sources": self._filtered_sources(q, category_filter),
            "excluded_sources": excluded_sources,
            "excluded_categories": excluded_categories,
            "categories": Source.CATEGORY_LABELS.items(),
            "q": q,
            "category_filter": category_filter,
            "my_sources": my_sources,
            "my_subscriptions": my_subscriptions,
        })
        return context

    def post(self, request, *args, **kwargs):
        profile = request.user.profile

        # IMPORTANT: the form only renders checkboxes for whatever search/
        # category filter was active (hidden q/category fields carry that
        # forward) — only THOSE sources' exclusion state can be inferred
        # from "present vs. absent" in POST data. A source outside the
        # current filter is untouched, not silently excluded.
        q = request.POST.get("q", "").strip()
        category_filter = request.POST.get("category_filter", "")
        in_scope_keys = set(self._filtered_sources(q, category_filter).values_list("key", flat=True))
        included_sources = set(request.POST.getlist("sources"))
        newly_excluded = in_scope_keys - included_sources
        newly_included = in_scope_keys & included_sources

        existing_exclusions = {e.value for e in profile.exclusions.filter(kind="source")}
        target_exclusions = (existing_exclusions - newly_included) | newly_excluded
        save_exclusions(profile, "source", target_exclusions)

        # Categories are a small fixed set (7) — always fully shown, safe to
        # replace wholesale from what's submitted.
        all_category_keys = set(self.CATEGORY_LABELS.keys())
        included_categories = set(request.POST.getlist("categories"))
        save_exclusions(profile, "category", all_category_keys - included_categories)

        messages.success(request, "Your source preferences were updated.")
        redirect_url = reverse("onboarding:sources")
        if q or category_filter:
            redirect_url += f"?q={q}&category={category_filter}"
        return redirect(redirect_url)


class AddSourceView(LoginRequiredMixin, View):
    """
    POST /onboarding/sources/add/ — {source_type, feed_url|channel_url,
    name, category}. Runs the AI-relevance gate (via a Celery round-trip to
    the pipeline's "interactive" queue, see apps.onboarding.source_submission)
    and shows the result as a message banner — "live relevance feedback" per
    the roadmap, just server-rendered rather than a client-side AJAX
    preview, matching this project's existing no-JS-framework convention.

    source_type is "rss" (default, backward-compatible with the original
    form) or "youtube" — the two submission functions share every other
    piece of logic (cap check, auto-subscribe), branching only on which
    Celery task/field the request needs.
    """

    def post(self, request, *args, **kwargs):
        category = request.POST.get("category") or "developer_communities"

        if request.POST.get("source_type") == "youtube":
            result = submit_youtube_source(
                request.user,
                channel_url=request.POST.get("channel_url", ""),
                name=request.POST.get("name", ""),
                category=category,
            )
        else:
            result = submit_source(
                request.user,
                feed_url=request.POST.get("feed_url", ""),
                name=request.POST.get("name", ""),
                category=category,
            )

        if result["ok"]:
            messages.success(request, result["message"])
        else:
            messages.error(request, result["message"])
        return redirect("onboarding:sources")


class UnsubscribeSourceView(LoginRequiredMixin, View):
    """POST /onboarding/sources/unsubscribe/<id>/ — drop this user's subscription to a user-submitted source."""

    def post(self, request, source_id, *args, **kwargs):
        deleted, _ = UserSourceSubscription.objects.filter(
            profile=request.user.profile, source_id=source_id,
        ).delete()
        if deleted:
            messages.success(request, "Unsubscribed.")
        return redirect("onboarding:sources")


class OnboardingWizardView(LoginRequiredMixin, View):
    """
    Soft/skippable 3-step wizard: persona -> interests -> sources. Reuses
    save_interests/save_exclusions (same as the standalone Preferences/
    Sources pages — no duplicated logic). Nothing here blocks access to the
    rest of the app; a user can leave mid-wizard and everything they've
    already submitted stays saved (onboarding_completed only flips True on
    reaching/skipping the final step).
    """

    template_name = "onboarding/wizard.html"
    STEPS = ("persona", "interests", "sources")

    def _step(self, request):
        step = request.GET.get("step") or request.POST.get("step") or "persona"
        return step if step in self.STEPS else "persona"

    def get(self, request, *args, **kwargs):
        profile = request.user.profile
        if profile.onboarding_completed:
            messages.info(request, "You've already completed onboarding — manage your choices from Preferences, Sources, or your Profile.")
            return redirect("onboarding:preferences")

        step = self._step(request)
        context = {"step": step, "step_index": self.STEPS.index(step) + 1, "total_steps": len(self.STEPS)}

        if step == "persona":
            context["personas"] = Persona.objects.filter(is_active=True)
            context["selected_persona_id"] = profile.persona_id
        elif step == "interests":
            interests_by_category = {}
            for interest in Interest.objects.filter(is_active=True):
                interests_by_category.setdefault(interest.category or "other", []).append(interest)
            context["interests_by_category"] = interests_by_category
            context["selected_ids"] = set(profile.interests.values_list("interest_id", flat=True))
        elif step == "sources":
            excluded_sources = {e.value for e in profile.exclusions.filter(kind="source")}
            context["sources"] = Source.objects.filter(is_active=True)
            context["excluded_sources"] = excluded_sources

        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        step = self._step(request)
        profile = request.user.profile
        skip = "skip" in request.POST

        if not skip:
            if step == "persona":
                profile.persona_id = request.POST.get("persona") or None
                profile.save(update_fields=["persona"])
            elif step == "interests":
                save_interests(profile, request.POST.getlist("interests"))
            elif step == "sources":
                all_keys = set(Source.objects.filter(is_active=True).values_list("key", flat=True))
                included = set(request.POST.getlist("sources"))
                save_exclusions(profile, "source", all_keys - included)

        next_index = self.STEPS.index(step) + 1
        if next_index < len(self.STEPS):
            return redirect(f"{reverse('onboarding:start')}?step={self.STEPS[next_index]}")

        profile.onboarding_completed = True
        profile.save(update_fields=["onboarding_completed"])
        messages.success(request, "You're all set! Your feed will personalize as digests run.")
        return redirect("feed")
