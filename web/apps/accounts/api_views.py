"""
JSON auth surface for the M15 frontend integration (see
.claude/plans/effervescent-petting-nebula.md):

  GET  /api/session/  — app-load hydration call (Phase 0). Two jobs in one
                         tiny endpoint: ensure_csrf_cookie guarantees the
                         `csrftoken` cookie is set on first load (the
                         frontend's api.ts client reads it for every
                         mutating request, mirroring the existing
                         beacon.js/assistant.js getCsrfToken() convention),
                         and it reports auth state + entitlements so
                         Zustand's isLoggedIn/user stop being a hardcoded
                         mock (frontend/src/lib/store.ts).
  POST /api/accounts/login/  — real login, JSON body {email, password}.
  POST /api/accounts/signup/ — real signup, JSON body {email, password1, password2, firstName?}.
  POST /api/accounts/logout/ — real logout.

Login/signup deliberately reuse the EXACT SAME business logic as the
existing template views (RegisterForm, login_rate_limit_ok,
send_verification_email) — only the request/response format changes from
HTML to JSON, so there is exactly one place each of those rules lives.

All four views return the SAME {isAuthenticated, user, entitlements} shape
as SessionView, so the frontend can funnel any auth action (login, signup,
logout, or the initial session check) through one response parser.
"""
import json

from django.contrib.auth import login, logout
from django.contrib.auth import authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse

from apps.onboarding.models import Persona

from .email_verification import send_verification_email
from .entitlements import FEATURE_PLANS, user_can
from .forms import BootstrapPasswordResetForm, RegisterForm
from .models import StripeCustomer, User
from .views import login_rate_limit_ok


def _session_payload(user) -> dict:
    if not user.is_authenticated:
        return {"isAuthenticated": False, "user": None, "entitlements": {}}
    return {
        "isAuthenticated": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "firstName": user.first_name,
            "plan": user.plan,
            "isStaff": user.is_staff,
            "emailVerified": user.email_verified,
            "onboardingCompleted": user.profile.onboarding_completed,
        },
        "entitlements": {feature: user_can(user, feature) for feature in FEATURE_PLANS},
    }


def _parse_json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "invalid JSON"}, status=400)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(View):

    def get(self, request, *args, **kwargs):
        return JsonResponse(_session_payload(request.user))


class LoginAPIView(View):
    """POST /api/accounts/login/ — {email, password} -> session payload.
    Rate limiting is IDENTICAL to the template login path (login_rate_limit_ok,
    apps.accounts.views) — same keys, same budget, shared not duplicated."""

    def post(self, request, *args, **kwargs):
        payload, error = _parse_json_body(request)
        if error is not None:
            return error

        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""

        if not login_rate_limit_ok(request, email):
            return JsonResponse(
                {"error": "Too many login attempts. Please wait a few minutes and try again."}, status=429
            )

        user = authenticate(request, username=email, password=password)
        if user is None:
            return JsonResponse({"error": "Incorrect email or password."}, status=400)

        login(request, user)
        return JsonResponse(_session_payload(user))


class SignupAPIView(View):
    """POST /api/accounts/signup/ — {email, password1, password2, firstName?}
    -> session payload. Reuses RegisterForm verbatim (the SAME uniqueness/
    password-confirmation/password-strength validation the template signup
    page enforces), auto-logs-in the new user, and sends the SAME
    verification email RegisterView sends — matching that view's behavior
    field-for-field, just returning JSON instead of a redirect."""

    def post(self, request, *args, **kwargs):
        payload, error = _parse_json_body(request)
        if error is not None:
            return error

        form = RegisterForm(data={
            "email": payload.get("email", ""),
            "first_name": payload.get("firstName", ""),
            "password1": payload.get("password1", ""),
            "password2": payload.get("password2", ""),
        })
        if not form.is_valid():
            # Flatten Django's per-field error-list shape into {field: [messages]}
            # -- the frontend's form (react-hook-form + zod) renders per-field
            # errors, so a flat {"error": "..."} string would lose which field.
            return JsonResponse({"errors": form.errors.get_json_data(escape_html=False)}, status=400)

        user = form.save()
        login(request, user)
        send_verification_email(user, request)
        return JsonResponse(_session_payload(user), status=201)


class LogoutAPIView(View):
    """POST /api/accounts/logout/ — always succeeds (logging out an
    already-anonymous session is a no-op, not an error)."""

    def post(self, request, *args, **kwargs):
        logout(request)
        return JsonResponse(_session_payload(request.user))


def _user_state_payload(user) -> dict:
    """Matches frontend/src/lib/types.ts's UserState shape field-for-field —
    this is what ProfilePage/BillingPage hydrate the global store's `user`
    from (replacing the honest-placeholder 0s/defaults store.ts's
    mapSessionUserToUserState sets from the minimal SessionUser alone;
    see that function's own comment). Reuses the EXACT SAME queries
    apps.accounts.views.ProfileView/BillingView already build their
    template context from."""
    from collections import Counter

    from apps.behavior.models import UserFollow
    from apps.behavior.views import FREE_FOLLOW_LIMIT
    from apps.catalog.models import DigestLog, Source
    from apps.onboarding.source_submission import FREE_CUSTOM_SOURCE_LIMIT

    profile = user.profile
    digest_settings = getattr(profile, "digest_settings", None)
    exclusions = list(profile.exclusions.all())
    excluded_categories = {e.value for e in exclusions if e.kind == "category"}
    excluded_sources = {e.value for e in exclusions if e.kind == "source"}
    interest_slugs = list(
        profile.interests.select_related("interest").order_by("-weight").values_list("interest__slug", flat=True)
    )

    return {
        "role": "staff" if user.is_staff else ("pro" if user.plan == "pro" else "free"),
        "name": user.first_name or user.email.split("@")[0],
        "email": user.email,
        "bio": profile.bio,
        "preferences": {
            "interests": interest_slugs,
            "persona": profile.persona.slug if profile.persona_id else None,
            "technicalLevel": digest_settings.expertise_level if digest_settings else "intermediate",
            "itemsPerFeed": digest_settings.max_items if digest_settings else 10,
            "articleVideoMix": digest_settings.format_balance if digest_settings else "balanced",
            "researchIndustryLean": digest_settings.topic_lean if digest_settings else "balanced",
            "readingTimeBudget": digest_settings.reading_time_budget_minutes if digest_settings else None,
            "digestFrequency": digest_settings.frequency if digest_settings else "daily",
            "digestPaused": digest_settings.is_paused if digest_settings else False,
            "excludedSources": sorted(excluded_sources),
            "excludedCategories": sorted(excluded_categories),
        },
        "customSourceCount": Source.objects.filter(created_by=user.id).count(),
        "followCount": UserFollow.objects.filter(user=user).count(),
        "maxCustomSources": None if user_can(user, "unlimited_custom_sources") else FREE_CUSTOM_SOURCE_LIMIT,
        "maxFollows": None if user_can(user, "unlimited_follows") else FREE_FOLLOW_LIMIT,
        "digestCount": DigestLog.objects.filter(user_id=user.id).count(),
        "isEmailVerified": user.email_verified,
        "onboardingComplete": profile.onboarding_completed,
        "plan": user.plan,
        "subscriptionEnd": (
            user.plan_expires_at.isoformat() if user.plan == "pro" and user.plan_expires_at else None
        ),
    }


class ProfileAPIView(LoginRequiredMixin, View):
    """GET/POST /api/accounts/profile/ — mirrors apps.accounts.views.ProfileView
    field-for-field. GET returns the full UserState shape (see
    _user_state_payload) plus two profile-page-only extras (favoriteSources,
    rankingCount) that aren't part of the global store's UserState."""

    def get(self, request, *args, **kwargs):
        from collections import Counter

        user = request.user
        rankings = list(user.rankings.all()[:50])
        source_counter = Counter()
        for r in rankings:
            obj = r.content_object
            if obj is None:
                continue
            source_counter[getattr(obj, "source", "youtube")] += 1

        return JsonResponse({
            **_user_state_payload(user),
            "favoriteSources": source_counter.most_common(5),
            "rankingCount": len(rankings),
        })

    def post(self, request, *args, **kwargs):
        """Body matches ProfilePage.tsx's local form state: {name, bio,
        persona (a slug or null), digestFrequency, digestPaused,
        technicalLevel, itemsPerFeed, articleVideoMix, researchIndustryLean,
        readingTimeBudget (minutes, nullable)} — same field-by-field
        validation as ProfileView.post(), just from a JSON body."""
        payload, error = _parse_json_body(request)
        if error is not None:
            return error

        user = request.user
        profile = user.profile

        user.first_name = (payload.get("name") or "").strip()
        user.save(update_fields=["first_name"])

        profile.bio = (payload.get("bio") or "").strip()
        persona_slug = payload.get("persona")
        if persona_slug:
            persona = Persona.objects.filter(slug=persona_slug, is_active=True).first()
            profile.persona_id = persona.id if persona else None
        else:
            profile.persona_id = None
        profile.save(update_fields=["bio", "persona"])

        settings_obj = getattr(profile, "digest_settings", None)
        if settings_obj is not None:
            frequency = payload.get("digestFrequency")
            if frequency in dict(settings_obj._meta.get_field("frequency").choices):
                settings_obj.frequency = frequency

            settings_obj.is_paused = bool(payload.get("digestPaused"))

            expertise_level = payload.get("technicalLevel")
            if expertise_level in dict(settings_obj._meta.get_field("expertise_level").choices):
                settings_obj.expertise_level = expertise_level

            format_balance = payload.get("articleVideoMix")
            if format_balance in dict(settings_obj._meta.get_field("format_balance").choices):
                settings_obj.format_balance = format_balance

            topic_lean = payload.get("researchIndustryLean")
            if topic_lean in dict(settings_obj._meta.get_field("topic_lean").choices):
                settings_obj.topic_lean = topic_lean

            items_per_feed = payload.get("itemsPerFeed")
            if isinstance(items_per_feed, int):
                settings_obj.max_items = max(5, min(50, items_per_feed))

            reading_time_budget = payload.get("readingTimeBudget")
            if reading_time_budget is None or reading_time_budget == "":
                settings_obj.reading_time_budget_minutes = None
            elif isinstance(reading_time_budget, int):
                settings_obj.reading_time_budget_minutes = max(1, min(120, reading_time_budget))

            settings_obj.save()

        return JsonResponse(_user_state_payload(user))


class BillingAPIView(LoginRequiredMixin, View):
    """GET /api/accounts/billing/ — mirrors apps.accounts.views.BillingView's
    usage stats exactly, plus real Stripe customer/subscription status."""

    def get(self, request, *args, **kwargs):
        from .billing import stripe_configured

        user = request.user
        customer = StripeCustomer.objects.filter(user=user).first()

        return JsonResponse({
            **_user_state_payload(user),
            "billingConfigured": stripe_configured(),
            "stripeCustomer": (
                {
                    "subscriptionStatus": customer.subscription_status,
                    "currentPeriodEnd": customer.current_period_end.isoformat() if customer.current_period_end else None,
                }
                if customer else None
            ),
        })


class CreateCheckoutSessionAPIView(LoginRequiredMixin, View):
    """POST /api/accounts/billing/checkout/ — JSON twin of
    apps.accounts.billing.CreateCheckoutSessionView: same email-verification
    gate, same Stripe Checkout session creation, but returns the session URL
    as JSON ({url}) instead of issuing an HTTP redirect, since a SPA
    navigates there itself (window.location.href = url)."""

    def post(self, request, *args, **kwargs):
        from django.urls import reverse

        import stripe
        from django.conf import settings

        from .billing import stripe_configured

        if not stripe_configured():
            return JsonResponse({"error": "Billing isn't configured yet on this deployment."}, status=503)
        if not request.user.email_verified:
            return JsonResponse({"error": "Please verify your email before upgrading."}, status=403)

        stripe.api_key = settings.STRIPE_SECRET_KEY
        existing = StripeCustomer.objects.filter(user=request.user).first()
        customer_kwargs = (
            {"customer": existing.stripe_customer_id} if existing else {"customer_email": request.user.email}
        )

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": settings.STRIPE_PRICE_ID_PRO, "quantity": 1}],
                success_url=(
                    request.build_absolute_uri(reverse("accounts:checkout_success"))
                    + "?session_id={CHECKOUT_SESSION_ID}"
                ),
                cancel_url=request.build_absolute_uri(reverse("accounts:checkout_cancel")),
                client_reference_id=str(request.user.id),
                **customer_kwargs,
            )
        except stripe.error.StripeError:
            return JsonResponse({"error": "Something went wrong starting checkout. Please try again shortly."}, status=502)

        return JsonResponse({"url": session.url})


class ResendVerificationAPIView(LoginRequiredMixin, View):
    """POST /api/accounts/verify/resend/ — resend the verification email to
    the logged-in user's own address, reusing send_verification_email()
    verbatim (same token generator, same email template). Replaces the
    classic apps.accounts.views.ResendVerificationView (a redirect+Django-
    messages flow with no JSON equivalent) — that view and its form's only
    caller (base.html's unverified-email banner) were both retired in
    M15 Phase 5 once this + ProfilePage.tsx's real button existed."""

    def post(self, request, *args, **kwargs):
        if request.user.email_verified:
            return JsonResponse({"ok": True, "alreadyVerified": True})
        if send_verification_email(request.user, request):
            return JsonResponse({"ok": True, "alreadyVerified": False})
        return JsonResponse({"error": "Couldn't send the verification email — please try again shortly."}, status=502)


class PasswordResetRequestAPIView(View):
    """POST /api/accounts/password-reset/ — {email} -> {ok: true}, always
    (never reveals whether the address has an account — same information
    -disclosure posture as Django's own PasswordResetForm/PasswordResetView).
    Reuses BootstrapPasswordResetForm.save() verbatim, so the email
    template, subject template, and token generator are the EXACT SAME ones
    the classic accounts:password_reset view already uses -- this is just a
    JSON front door onto that one save() call for ForgotPasswordPage.tsx."""

    def post(self, request, *args, **kwargs):
        payload, error = _parse_json_body(request)
        if error is not None:
            return error

        form = BootstrapPasswordResetForm(data={"email": payload.get("email", "")})
        if form.is_valid():
            form.save(
                request=request,
                subject_template_name="registration/password_reset_subject.txt",
                email_template_name="registration/password_reset_email.html",
            )
        return JsonResponse({"ok": True})


class OpsAPIView(LoginRequiredMixin, View):
    """GET /api/accounts/ops/ — staff-only (mirrors apps.accounts.ops.
    OpsDashboardView's is_staff test_func + its exact source-health query
    and is_unhealthy computation field-for-field), for the recreated
    OpsPage.tsx (M15 — no Django-rendered ops dashboard equivalent existed
    in the Z.ai frontend, see the integration plan's Phase 4)."""

    def get(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({"error": "Staff access required."}, status=403)

        from apps.catalog.models import Source

        sources = list(Source.objects.all().order_by("category", "name"))
        for source in sources:
            source.is_unhealthy = bool(
                source.is_active
                and source.last_run_at is not None
                and (source.last_success_at is None or source.last_success_at < source.last_run_at)
            )

        return JsonResponse({
            "totalCount": len(sources),
            "activeCount": sum(1 for s in sources if s.is_active),
            "unhealthyCount": sum(1 for s in sources if s.is_unhealthy),
            "sources": [
                {
                    "key": s.key,
                    "name": s.name,
                    "category": s.category_label,
                    "isActive": s.is_active,
                    "isUnhealthy": s.is_unhealthy,
                    "visibility": s.visibility,
                    "lastRunAt": s.last_run_at.isoformat() if s.last_run_at else None,
                    "lastSuccessAt": s.last_success_at.isoformat() if s.last_success_at else None,
                }
                for s in sources
            ],
        })


class BillingPortalAPIView(LoginRequiredMixin, View):
    """POST /api/accounts/billing/portal/ — JSON twin of
    apps.accounts.billing.BillingPortalView, returns {url} instead of redirecting."""

    def post(self, request, *args, **kwargs):
        import stripe
        from django.conf import settings

        from .billing import stripe_configured

        customer = StripeCustomer.objects.filter(user=request.user).first()
        if not stripe_configured() or customer is None:
            return JsonResponse({"error": "No active subscription to manage."}, status=404)

        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            portal_session = stripe.billing_portal.Session.create(
                customer=customer.stripe_customer_id,
                return_url=request.build_absolute_uri("/billing"),
            )
        except stripe.error.StripeError:
            return JsonResponse({"error": "Couldn't open the billing portal. Please try again shortly."}, status=502)

        return JsonResponse({"url": portal_session.url})
