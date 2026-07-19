from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .billing import (
    BillingPortalView,
    CheckoutCancelView,
    CheckoutSuccessView,
    CreateCheckoutSessionView,
    StripeWebhookView,
)
from .forms import BootstrapPasswordResetForm, BootstrapSetPasswordForm
from .views import (
    BillingView,
    ProfileView,
    RateLimitedLoginView,
    RegisterView,
    ResendVerificationView,
    VerifyEmailView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", RateLimitedLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("profile/", ProfileView.as_view(), name="profile"),

    # M13 — email verification (soft-gated app access, hard-gated checkout).
    path("verify/<uidb64>/<token>/", VerifyEmailView.as_view(), name="verify_email"),
    path("verify/resend/", ResendVerificationView.as_view(), name="resend_verification"),

    # M13 — password reset: Django's own built-in views, no new package.
    path(
        "password_reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            form_class=BootstrapPasswordResetForm,
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            form_class=BootstrapSetPasswordForm,
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"),
        name="password_reset_complete",
    ),

    # M13 — billing/usage page + Stripe Checkout/Portal/webhook.
    path("billing/", BillingView.as_view(), name="billing"),
    path("stripe/checkout/", CreateCheckoutSessionView.as_view(), name="create_checkout_session"),
    path("stripe/checkout/success/", CheckoutSuccessView.as_view(), name="checkout_success"),
    path("stripe/checkout/cancel/", CheckoutCancelView.as_view(), name="checkout_cancel"),
    path("stripe/portal/", BillingPortalView.as_view(), name="billing_portal"),
    path("stripe/webhook/", StripeWebhookView.as_view(), name="stripe_webhook"),
]
