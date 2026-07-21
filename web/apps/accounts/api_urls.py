from django.urls import path

from .api_views import (
    BillingAPIView, BillingPortalAPIView, CreateCheckoutSessionAPIView, LoginAPIView, LogoutAPIView,
    OpsAPIView, PasswordResetRequestAPIView, ProfileAPIView, ResendVerificationAPIView, SignupAPIView,
)

app_name = "accounts_api"

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="login"),
    path("signup/", SignupAPIView.as_view(), name="signup"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("profile/", ProfileAPIView.as_view(), name="profile"),
    path("billing/", BillingAPIView.as_view(), name="billing"),
    path("billing/checkout/", CreateCheckoutSessionAPIView.as_view(), name="billing_checkout"),
    path("billing/portal/", BillingPortalAPIView.as_view(), name="billing_portal"),
    path("password-reset/", PasswordResetRequestAPIView.as_view(), name="password_reset"),
    path("ops/", OpsAPIView.as_view(), name="ops"),
    path("verify/resend/", ResendVerificationAPIView.as_view(), name="resend_verification"),
]
