# web/apps/accounts/billing.py
#
# M13 — Stripe Checkout (hosted page, test mode) + Billing Portal + webhook.
# Checkout/Portal avoid PCI scope entirely — Stripe hosts the actual payment
# form, no card data ever touches this app.
#
# The webhook is the ONLY writer of StripeCustomer and the ONLY thing that
# ever flips User.plan/plan_expires_at — CheckoutSuccessView (the page
# Stripe redirects the browser to) does NOT grant Pro itself, since an
# attacker could otherwise just GET that URL directly without ever paying.
# Every other entitlement check in the app (user_can(), FEATURE_PLANS, M11's
# DjangoUser pipeline mirror) keeps reading the SAME two User fields it
# always has — this milestone activates enforcement, it doesn't add a new
# parallel plan-state.

import logging
from datetime import datetime, timezone as dt_timezone

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import StripeCustomer, User

logger = logging.getLogger(__name__)


def stripe_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID_PRO)


class CheckoutSuccessView(LoginRequiredMixin, View):
    """
    GET — Stripe redirects the browser here after a completed Checkout.
    Does NOT grant Pro itself (see module docstring) — just an honest
    "processing" message; the webhook has usually already landed by the time
    this page loads, but there's no hard guarantee of ordering, so the
    copy deliberately doesn't promise "you're Pro now" as a fact.

    Redirects to the real SPA path (/billing), NOT the accounts:billing URL
    name — that classic Django template view is gone (M15), but this view
    itself stays: CreateCheckoutSessionAPIView (the live JSON checkout
    endpoint the SPA actually calls) still points Stripe's success_url at
    THIS view's URL name (reverse("accounts:checkout_success")), so real
    paid checkouts land here regardless of which frontend started them.
    """

    def get(self, request, *args, **kwargs):
        messages.success(request, "Thanks! Your upgrade is processing — this usually takes just a few seconds.")
        return redirect("/billing")


class CheckoutCancelView(LoginRequiredMixin, View):
    """See CheckoutSuccessView's docstring — same "still live, redirect
    target repointed to the SPA path" reasoning applies here."""

    def get(self, request, *args, **kwargs):
        messages.info(request, "Checkout canceled — no changes were made.")
        return redirect("/pricing")


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

def _handle_checkout_completed(session_obj: dict) -> None:
    user_id = session_obj.get("client_reference_id")
    stripe_customer_id = session_obj.get("customer")
    stripe_subscription_id = session_obj.get("subscription")
    if not user_id or not stripe_customer_id:
        logger.error("checkout.session.completed missing client_reference_id/customer: %r", session_obj)
        return

    try:
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError):
        logger.error("checkout.session.completed: no such user_id=%r", user_id)
        return

    StripeCustomer.objects.update_or_create(
        user=user,
        defaults={
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "subscription_status": "active",
        },
    )
    # Provisional grant — customer.subscription.updated (sent by Stripe
    # around the same time for a subscription-mode session) supplies the
    # real current_period_end and is what keeps plan_expires_at accurate
    # going forward; this event alone doesn't carry a period-end.
    user.plan = User.Plan.PRO
    user.save(update_fields=["plan"])
    logger.info("Stripe checkout completed: user_id=%s now Pro (subscription=%s)", user_id, stripe_subscription_id)


def _handle_subscription_updated(sub_obj: dict) -> None:
    stripe_customer_id = sub_obj.get("customer")
    status = sub_obj.get("status")
    current_period_end = sub_obj.get("current_period_end")

    customer = (
        StripeCustomer.objects.filter(stripe_customer_id=stripe_customer_id).select_related("user").first()
    )
    if customer is None:
        logger.warning("customer.subscription.updated for unknown stripe_customer_id=%r", stripe_customer_id)
        return

    customer.stripe_subscription_id = sub_obj.get("id")
    customer.subscription_status = status
    customer.current_period_end = (
        datetime.fromtimestamp(current_period_end, tz=dt_timezone.utc) if current_period_end else None
    )
    customer.save()

    user = customer.user
    if status in ("active", "trialing"):
        user.plan = User.Plan.PRO
        user.plan_expires_at = customer.current_period_end
    else:
        user.plan = User.Plan.FREE
        user.plan_expires_at = None
    user.save(update_fields=["plan", "plan_expires_at"])
    logger.info("Stripe subscription updated: user_id=%s status=%s plan=%s", user.id, status, user.plan)


def _handle_subscription_deleted(sub_obj: dict) -> None:
    stripe_customer_id = sub_obj.get("customer")
    customer = (
        StripeCustomer.objects.filter(stripe_customer_id=stripe_customer_id).select_related("user").first()
    )
    if customer is None:
        return

    customer.subscription_status = "canceled"
    customer.save(update_fields=["subscription_status"])

    user = customer.user
    user.plan = User.Plan.FREE
    user.plan_expires_at = None
    user.save(update_fields=["plan", "plan_expires_at"])
    logger.info("Stripe subscription deleted: user_id=%s reverted to Free", user.id)


_EVENT_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
}


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    """
    POST /accounts/stripe/webhook/ — Stripe calls this server-to-server, so
    it carries no session cookie/CSRF token (same reasoning as
    apps.behavior.views.EventIngestView's sendBeacon exemption); the real
    protection here is Stripe's own HMAC signature, verified below, not
    Origin/Referer matching.
    """

    def post(self, request, *args, **kwargs):
        if not settings.STRIPE_WEBHOOK_SECRET:
            logger.error("Stripe webhook received but STRIPE_WEBHOOK_SECRET is unset — rejecting")
            return HttpResponseBadRequest("webhook not configured")

        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            logger.warning("Stripe webhook signature/payload verification failed: %s", exc)
            return HttpResponseBadRequest("invalid payload or signature")

        handler = _EVENT_HANDLERS.get(event["type"])
        if handler is not None:
            # construct_event() returns a StripeObject, not a plain dict —
            # it supports [] access but NOT .get() (confirmed live: a bare
            # StripeObject crashes every handler below with
            # AttributeError: 'get' the first time a real signed event is
            # processed, since __getattr__ proxies missing keys to __getitem__
            # instead of returning None). .to_dict() gives the handlers the
            # plain-dict .get() semantics they're written against.
            handler(event["data"]["object"].to_dict())
        else:
            logger.info("Stripe webhook: unhandled event type %s", event["type"])

        return HttpResponse(status=200)
