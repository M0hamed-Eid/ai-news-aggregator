from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .billing import CheckoutCancelView, CheckoutSuccessView, StripeWebhookView
from .forms import BootstrapSetPasswordForm
from .views import VerifyEmailView

app_name = "accounts"

urlpatterns = [
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # M13 — email verification (soft-gated app access, hard-gated checkout).
    # The resend-verification form used to live here too (classic
    # ResendVerificationView) — retired in M15 Phase 5 once
    # ResendVerificationAPIView (api_views.py) + ProfilePage.tsx's real
    # "Resend verification email" button replaced it.
    path("verify/<uidb64>/<token>/", VerifyEmailView.as_view(), name="verify_email"),

    # M13 — password reset. The REQUEST step (password_reset/,
    # password_reset/done/) is retired (M15 Phase 5): ForgotPasswordPage.tsx
    # + PasswordResetRequestAPIView (api_views.py) replace it entirely. The
    # CONFIRM/COMPLETE steps stay classic Django server-rendered pages
    # (reached only via emailed links, restyled to match the SPA in
    # M15 Phase 4) since Django's built-in PasswordResetConfirmView/
    # PasswordResetCompleteView are what the emailed link actually points at.
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            form_class=BootstrapSetPasswordForm,
            success_url=reverse_lazy("accounts:password_reset_complete"),
            # "Request a new link" on the invalid/expired branch is a relative
            # /forgot-password href -- only resolves when this page is loaded
            # through the Vercel domain (which owns that Next.js route), not
            # when hit directly on the IP-only Django backend. FRONTEND_BASE_URL
            # is the same setting apps.accounts.views.frontend_redirect() uses
            # for the identical split-domain problem.
            extra_context={"frontend_base_url": getattr(settings, "FRONTEND_BASE_URL", "")},
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"),
        name="password_reset_complete",
    ),

    # M13 — Stripe Checkout/Portal redirect targets + webhook. The forms
    # that used to POST to create-checkout-session/billing-portal here
    # (billing.html/pricing.html) are retired (M15 Phase 5) —
    # CreateCheckoutSessionAPIView/BillingPortalAPIView (api_views.py) are
    # the live entry points now — but Stripe still redirects the browser to
    # these two URL names after a real checkout completes/cancels (see
    # CheckoutSuccessView's own docstring), so they stay.
    path("stripe/checkout/success/", CheckoutSuccessView.as_view(), name="checkout_success"),
    path("stripe/checkout/cancel/", CheckoutCancelView.as_view(), name="checkout_cancel"),
    path("stripe/webhook/", StripeWebhookView.as_view(), name="stripe_webhook"),
]
