"""
Auto-create per-user personalization rows on signup.

Fires unconditionally on every new User — this is what makes onboarding
SOFT/SKIPPABLE: a brand new user already has a UserProfile (persona=None,
onboarding_completed=False) and UserDigestSettings (all defaults) before they
ever see an onboarding screen, so the dashboard/digest never has to gate on
"has this user finished onboarding". No UserExclusion rows are created here —
absence of an exclusion means "included", so a zero-row user already gets
everything by default (see apps.onboarding.models.UserExclusion).
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_profile(sender, instance, created, **kwargs):
    if not created:
        return

    from apps.onboarding.models import UserDigestSettings

    from .models import UserProfile

    profile = UserProfile.objects.create(user=instance)
    UserDigestSettings.objects.create(profile=profile)
