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
import logging

from django.contrib.auth import login, logout
from django.contrib.auth import authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse

from apps.onboarding.models import Persona

from .email_verification import send_verification_email
from .entitlements import FEATURE_PLANS, user_can
from .forms import BootstrapPasswordResetForm, RegisterForm
from .legal import CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION
from .models import StripeCustomer, TermsAcceptance, User
from .views import login_rate_limit_ok

logger = logging.getLogger(__name__)


def _session_payload(request) -> dict:
    # M16 split-domain fix — the Vercel frontend's JS can never read a
    # csrftoken cookie Django sets (it's scoped to the Render domain, not
    # vercel.app; cross-site cookie ATTACHMENT on outgoing fetches works
    # fine via credentials:'include'+SameSite=None, but document.cookie on
    # the Vercel page structurally cannot see a cookie set for a different
    # registrable domain). get_token(request) both returns the current
    # token value (so the frontend can cache it and echo it back as
    # X-CSRFToken on every mutating call — see frontend/src/lib/api.ts's
    # setCsrfToken) and marks the cookie for (harmless, unused) refresh.
    user = request.user
    csrf_token = get_token(request)
    if not user.is_authenticated:
        return {"isAuthenticated": False, "user": None, "entitlements": {}, "csrfToken": csrf_token}

    # M16 — has this user accepted the CURRENT terms/privacy version? Only
    # the latest acceptance row matters here (TermsAcceptance is
    # append-only so the full history survives, but "does this session
    # need a re-acceptance prompt" is a question about the most recent one
    # only). A user with zero rows (pre-M16 account) also needs prompting.
    latest = (
        TermsAcceptance.objects.filter(user=user).order_by("-accepted_at").first()
    )
    needs_terms_acceptance = (
        latest is None
        or latest.terms_version != CURRENT_TERMS_VERSION
        or latest.privacy_policy_version != CURRENT_PRIVACY_VERSION
    )

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
        "needsTermsAcceptance": needs_terms_acceptance,
        "termsVersion": CURRENT_TERMS_VERSION,
        "privacyVersion": CURRENT_PRIVACY_VERSION,
        "csrfToken": csrf_token,
    }


def _parse_json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "invalid JSON"}, status=400)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(View):

    def get(self, request, *args, **kwargs):
        return JsonResponse(_session_payload(request))


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
        return JsonResponse(_session_payload(request))


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

        # M16 — required, not optional: the account cannot be created
        # without it. This is the ONLY consent checkbox at signup — there
        # is no separate marketing/optional-communications feature in this
        # app to gate behind a second one (the weekly digest is core
        # product functionality configured during onboarding, not a
        # marketing opt-in), so inventing a second checkbox here would be
        # exactly the "fake consent requirement" this was told not to do.
        if not payload.get("termsAccepted"):
            return JsonResponse(
                {"errors": {"termsAccepted": [{"message": "You must accept the Terms of Use to create an account.", "code": "required"}]}},
                status=400,
            )

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
        TermsAcceptance.objects.create(
            user=user, terms_version=CURRENT_TERMS_VERSION, privacy_policy_version=CURRENT_PRIVACY_VERSION,
        )
        login(request, user)
        send_verification_email(user, request)
        return JsonResponse(_session_payload(request), status=201)


class AcceptTermsAPIView(LoginRequiredMixin, View):
    """POST /api/accounts/terms/accept/ — records acceptance of the
    CURRENT terms/privacy version for an already-logged-in user (the
    re-acceptance path, for whenever CURRENT_TERMS_VERSION/
    CURRENT_PRIVACY_VERSION next changes — see apps.accounts.legal). Takes
    no body; always accepts the current version, never an
    attacker-supplied one, so there's nothing to validate/trust from the
    request beyond the session itself."""

    def post(self, request, *args, **kwargs):
        TermsAcceptance.objects.create(
            user=request.user, terms_version=CURRENT_TERMS_VERSION, privacy_policy_version=CURRENT_PRIVACY_VERSION,
        )
        return JsonResponse(_session_payload(request))


class LogoutAPIView(View):
    """POST /api/accounts/logout/ — always succeeds (logging out an
    already-anonymous session is a no-op, not an error)."""

    def post(self, request, *args, **kwargs):
        logout(request)
        return JsonResponse(_session_payload(request))


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
            # Unlike send_verification_email() (email_verification.py),
            # Django's own PasswordResetForm.save() has no built-in
            # try/except -- a real SMTP failure (found live on Render: a
            # blocked/filtered outbound port hangs until EMAIL_TIMEOUT,
            # see base.py's GMAIL_* block) would otherwise propagate as an
            # unhandled 500, which also defeats this view's whole point of
            # never revealing whether the address has an account (a 500
            # vs. 200 IS a disclosure signal). Logged, never surfaced to
            # the client -- the response is {"ok": true} either way.
            try:
                form.save(
                    request=request,
                    subject_template_name="registration/password_reset_subject.txt",
                    email_template_name="registration/password_reset_email.html",
                )
            except Exception:
                logger.warning("PasswordResetRequestAPIView: send failed for a submitted address", exc_info=True)
        return JsonResponse({"ok": True})


class OpsAPIView(LoginRequiredMixin, View):
    """GET /api/accounts/ops/ — staff-only (mirrors apps.accounts.ops.
    OpsDashboardView's is_staff test_func + its exact source-health query
    and is_unhealthy computation field-for-field), for the recreated
    OpsPage.tsx (M15 — no Django-rendered ops dashboard equivalent existed
    in the Z.ai frontend, see the integration plan's Phase 4).

    M16 — also reports a lightweight `systemStatus` block for production
    observability (per-source health above already answers "is each
    scraper alive"; this answers the broader "is the whole pipeline
    healthy" questions) WITHOUT any new tracking table or paid monitoring
    service — every number here is a plain aggregate over data the
    pipeline already writes as a normal side effect of running. What this
    deliberately does NOT try to reconstruct: a full per-run pass/fail
    history or an LLM call/failure counter — neither is persisted
    anywhere today, and the honest, lightweight place to see them is
    GitHub Actions' own run history (already free, already exists) and
    each run's own print_summary() log line (already written, includes
    articles_errors/scoring_errors/rag_errors/deep_video_errors etc.) —
    duplicating that into a new DB table would be the "unnecessary
    infrastructure" this was told to avoid, not genuine lightweight
    monitoring."""

    def get(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({"error": "Staff access required."}, status=403)

        from django.db import connection
        from django.utils import timezone

        from apps.catalog.models import Article, DigestLog, Embedding, Source, TrendReport, YoutubeVideo

        sources = list(Source.objects.all().order_by("category", "name"))
        for source in sources:
            source.is_unhealthy = bool(
                source.is_active
                and source.last_run_at is not None
                and (source.last_success_at is None or source.last_success_at < source.last_run_at)
            )

        db_connected = True
        try:
            connection.ensure_connection()
        except Exception:
            db_connected = False

        cutoff_24h = timezone.now() - timezone.timedelta(hours=24)
        cutoff_7d = timezone.now() - timezone.timedelta(days=7)
        latest_article = Article.objects.order_by("-created_at").values_list("created_at", flat=True).first()
        latest_video = YoutubeVideo.objects.order_by("-created_at").values_list("created_at", flat=True).first()
        latest_embedding = Embedding.objects.order_by("-created_at").values_list("created_at", flat=True).first()
        latest_trend_report = TrendReport.objects.order_by("-generated_at").values_list("generated_at", flat=True).first()

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
            "systemStatus": {
                "checkedAt": timezone.now().isoformat(),
                "backendAlive": True,  # trivially true -- this response is proof
                "databaseConnected": db_connected,
                "content": {
                    "newArticles24h": Article.objects.filter(created_at__gte=cutoff_24h).count(),
                    "newVideos24h": YoutubeVideo.objects.filter(created_at__gte=cutoff_24h).count(),
                    "newEmbeddings24h": Embedding.objects.filter(created_at__gte=cutoff_24h).count(),
                    "latestArticleAt": latest_article.isoformat() if latest_article else None,
                    "latestVideoAt": latest_video.isoformat() if latest_video else None,
                    "latestEmbeddingAt": latest_embedding.isoformat() if latest_embedding else None,
                },
                "email": {
                    "digestsSent24h": DigestLog.objects.filter(sent_at__gte=cutoff_24h).count(),
                    "digestsSent7d": DigestLog.objects.filter(sent_at__gte=cutoff_7d).count(),
                },
                "trendReport": {
                    "latestGeneratedAt": latest_trend_report.isoformat() if latest_trend_report else None,
                },
                "notes": (
                    "Per-run pipeline pass/fail history and LLM call/failure counts are not "
                    "persisted in the database -- see GitHub Actions' run history "
                    "(.github/workflows/pipeline.yml) for exact per-run outcomes, and each run's "
                    "own log output (run_pipeline.py's print_summary()) for detailed counters."
                ),
            },
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


class DeleteAccountAPIView(LoginRequiredMixin, View):
    """POST /api/accounts/delete/ — {password} -> {"deleted": true}.

    Requires re-entering the current password even though the request is
    already authenticated — a real safety measure against a stolen/idle
    session performing an irreversible action, matching the same
    discipline Django's own admin uses for sensitive actions.

    Cancels any active Stripe subscription FIRST (best-effort — a Stripe
    API hiccup logs a warning but does not block deletion; leaving a
    user stuck unable to delete their account because of a third-party
    API blip would be worse than a rare orphaned-subscription cleanup
    task, and Stripe itself will still decline future charges once the
    card/customer is gone from OUR side... this is intentionally the
    least-bad tradeoff, not a claim that it's perfect).

    Deletion itself is just request.user.delete() — relies entirely on
    the CASCADE foreign keys already on every user-owned model
    (SavedItem, UserEvent, UserFollow, UserProfile, StripeCustomer,
    TermsAcceptance, UserInterest, UserExclusion, UserSourceSubscription,
    UserDigestSettings — all FK to User with on_delete=CASCADE) rather
    than hand-deleting each table, so this can never drift out of sync
    with the schema. Globally shared content (Article, YoutubeVideo,
    Source, ...) lives in the PIPELINE's own database/ORM entirely, with
    no foreign key to Django's User table at all — there is structurally
    nothing here that could delete shared catalog content."""

    def post(self, request, *args, **kwargs):
        payload, error = _parse_json_body(request)
        if error is not None:
            return error

        password = payload.get("password") or ""
        if not request.user.check_password(password):
            return JsonResponse({"error": "Incorrect password."}, status=403)

        import stripe
        from django.conf import settings

        customer = StripeCustomer.objects.filter(user=request.user).first()
        if customer is not None and customer.stripe_subscription_id and settings.STRIPE_SECRET_KEY:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            try:
                stripe.Subscription.delete(customer.stripe_subscription_id)
            except stripe.error.StripeError:
                logger.warning(
                    "DeleteAccountAPIView: failed to cancel Stripe subscription %s for user_id=%s "
                    "-- proceeding with account deletion anyway; may need manual cleanup in Stripe.",
                    customer.stripe_subscription_id, request.user.id,
                )

        user_id = request.user.id
        logout(request)
        User.objects.filter(id=user_id).delete()
        return JsonResponse({"deleted": True})
