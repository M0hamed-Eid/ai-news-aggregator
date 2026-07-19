from django.contrib import messages
from django.contrib.auth import login, views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.generic import CreateView, TemplateView

from apps.behavior.ratelimit import check_rate_limit
from apps.catalog.models import DigestLog, Source
from apps.onboarding.models import Persona
from apps.onboarding.source_submission import FREE_CUSTOM_SOURCE_LIMIT

from .email_verification import email_verification_token, send_verification_email
from .entitlements import user_can
from .forms import BootstrapAuthenticationForm, RegisterForm
from .models import StripeCustomer, User


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
        if send_verification_email(self.object, self.request):
            messages.info(self.request, "We've sent a verification link to your email.")
        else:
            messages.warning(
                self.request,
                "We couldn't send a verification email right now — use \"Resend verification email\" "
                "above once you're ready to verify.",
            )
        return response


class RateLimitedLoginView(auth_views.LoginView):
    """
    M13 — auth hardening. Wraps Django's built-in LoginView with the SAME
    Redis-backed limiter apps.behavior.ratelimit already uses for the M7
    event-ingestion endpoint, reused here rather than adding a new
    rate-limiting package. Keyed on BOTH the client IP (blocks distributed
    brute force) and the submitted email (blocks a targeted attack against
    one account from many IPs) — every POST consumes from both budgets
    regardless of whether the credentials turn out to be valid.
    """

    template_name = "registration/login.html"
    authentication_form = BootstrapAuthenticationForm
    redirect_authenticated_user = True

    LOGIN_ATTEMPT_LIMIT = 5
    LOGIN_ATTEMPT_WINDOW_SECONDS = 300

    def post(self, request, *args, **kwargs):
        ip = request.META.get("REMOTE_ADDR") or "unknown"
        email = (request.POST.get("username") or "").strip().lower()

        ip_ok = check_rate_limit(f"login_attempt:ip:{ip}", self.LOGIN_ATTEMPT_LIMIT, self.LOGIN_ATTEMPT_WINDOW_SECONDS)
        email_ok = (
            check_rate_limit(f"login_attempt:email:{email}", self.LOGIN_ATTEMPT_LIMIT, self.LOGIN_ATTEMPT_WINDOW_SECONDS)
            if email else True
        )

        if not (ip_ok and email_ok):
            form = self.get_form()
            form.add_error(None, "Too many login attempts. Please wait a few minutes and try again.")
            return self.form_invalid(form)

        return super().post(request, *args, **kwargs)


class VerifyEmailView(View):
    """GET /accounts/verify/<uidb64>/<token>/ — the link sent by send_verification_email()."""

    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and email_verification_token.check_token(user, token):
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            messages.success(request, "Your email is verified.")
        else:
            messages.error(request, "That verification link is invalid or has already been used.")

        return redirect("home" if request.user.is_authenticated else "accounts:login")


class ResendVerificationView(LoginRequiredMixin, View):
    """POST-only — resend the verification email to the logged-in user's own address."""

    def post(self, request, *args, **kwargs):
        if request.user.email_verified:
            messages.info(request, "Your email is already verified.")
        elif send_verification_email(request.user, request):
            messages.success(request, "Verification email sent.")
        else:
            messages.error(request, "Couldn't send the verification email — please try again shortly.")
        return redirect(request.META.get("HTTP_REFERER") or "accounts:profile")


class BillingView(LoginRequiredMixin, TemplateView):
    """
    M13 — subscription status + usage stats in one page (not fragmented
    into two), matching how ProfileView already combines several related
    concerns into one page rather than many thin ones. Stripe state is
    READ here only — every write happens in apps.accounts.billing's webhook.
    """

    template_name = "registration/billing.html"

    def get_context_data(self, **kwargs):
        from apps.behavior.models import UserFollow
        from apps.behavior.views import FREE_FOLLOW_LIMIT

        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["stripe_customer"] = StripeCustomer.objects.filter(user=user).first()

        # Usage stats — real counts against the SAME limits FollowToggleView/
        # submit_source actually enforce, not duplicated magic numbers.
        ctx["sources_used"] = Source.objects.filter(created_by=user.id).count()
        ctx["sources_limit"] = None if user_can(user, "unlimited_custom_sources") else FREE_CUSTOM_SOURCE_LIMIT
        ctx["follows_used"] = UserFollow.objects.filter(user=user).count()
        ctx["follows_limit"] = None if user_can(user, "unlimited_follows") else FREE_FOLLOW_LIMIT
        ctx["digests_received_count"] = DigestLog.objects.filter(user_id=user.id).count()
        return ctx


class PricingView(TemplateView):
    """
    Public — works for anonymous visitors (wired at the project root, same
    convention as HomeView/TrendReportView, not namespaced under accounts:).
    Mirrors docs/ROADMAP.md §5's Free/Pro table content directly rather than
    inventing new copy.
    """

    template_name = "registration/pricing.html"

    def get_context_data(self, **kwargs):
        from apps.behavior.views import FREE_FOLLOW_LIMIT

        from .billing import stripe_configured

        ctx = super().get_context_data(**kwargs)
        ctx["billing_configured"] = stripe_configured()
        ctx["free_follow_limit"] = FREE_FOLLOW_LIMIT
        return ctx


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

            # Ranking preferences (M9) — these were previously either inert
            # (expertise_level/content_depth had no form control anywhere)
            # or didn't exist (format_balance/topic_lean/reading_time_budget).
            # RankingService reads all of these as real scoring inputs now.
            expertise_level = request.POST.get("expertise_level")
            if expertise_level in dict(settings_obj._meta.get_field("expertise_level").choices):
                settings_obj.expertise_level = expertise_level

            format_balance = request.POST.get("format_balance")
            if format_balance in dict(settings_obj._meta.get_field("format_balance").choices):
                settings_obj.format_balance = format_balance

            topic_lean = request.POST.get("topic_lean")
            if topic_lean in dict(settings_obj._meta.get_field("topic_lean").choices):
                settings_obj.topic_lean = topic_lean

            try:
                max_items = int(request.POST.get("max_items", ""))
                settings_obj.max_items = max(5, min(50, max_items))
            except (TypeError, ValueError):
                pass

            budget_raw = request.POST.get("reading_time_budget_minutes", "").strip()
            if not budget_raw:
                settings_obj.reading_time_budget_minutes = None
            else:
                try:
                    settings_obj.reading_time_budget_minutes = max(1, min(120, int(budget_raw)))
                except (TypeError, ValueError):
                    pass

            settings_obj.save()

        messages.success(request, "Profile updated.")
        return redirect("accounts:profile")
