# web/apps/accounts/ops.py
#
# M13 — scraper health / ops dashboard. Staff-only (Django's built-in
# is_staff on AbstractUser — no new permission system). Reads
# apps.catalog.models.Source, the ALREADY-EXISTING read-only pipeline
# mirror (has last_run_at/last_success_at/is_active/category/visibility
# since M10) — zero new pipeline-side schema this milestone.

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView

from apps.catalog.models import Source


class OpsDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "registration/ops_dashboard.html"

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sources = list(Source.objects.all().order_by("category", "name"))

        for source in sources:
            # "Unhealthy" = active, has been run at least once, and its MOST
            # RECENT attempt did not succeed (last_success_at is null, or
            # strictly older than last_run_at). Flags a deliberately-broken
            # feed after exactly one bad run — no consecutive-failure
            # counter needed, matches the success criterion's literal wording.
            source.is_unhealthy = bool(
                source.is_active
                and source.last_run_at is not None
                and (source.last_success_at is None or source.last_success_at < source.last_run_at)
            )

        ctx["sources"] = sources
        ctx["total_count"] = len(sources)
        ctx["active_count"] = sum(1 for s in sources if s.is_active)
        ctx["unhealthy_count"] = sum(1 for s in sources if s.is_unhealthy)
        return ctx
