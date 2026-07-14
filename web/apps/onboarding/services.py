# web/apps/onboarding/services.py
#
# Shared write-paths for interest/exclusion updates, used by BOTH the
# standalone Preferences/Sources pages and the onboarding wizard steps —
# one place to update UserInterest/UserExclusion, no duplicated form logic
# between "set this up now" (wizard) and "change this later" (preferences).

from .models import Interest, UserExclusion, UserInterest


def save_interests(profile, interest_ids):
    """Replace a profile's UserInterest rows with exactly the given interest IDs (weight=1.0)."""
    interest_ids = {int(i) for i in interest_ids if str(i).isdigit()}
    profile.interests.exclude(interest_id__in=interest_ids).delete()
    existing_ids = set(profile.interests.values_list("interest_id", flat=True))
    to_create = [
        UserInterest(profile=profile, interest_id=iid)
        for iid in interest_ids - existing_ids
        if Interest.objects.filter(id=iid, is_active=True).exists()
    ]
    if to_create:
        UserInterest.objects.bulk_create(to_create)


def save_exclusions(profile, kind, values):
    """Replace a profile's UserExclusion rows of one `kind` ('category'|'source') with exactly `values`."""
    values = {v for v in values if v}
    profile.exclusions.filter(kind=kind).exclude(value__in=values).delete()
    existing = set(profile.exclusions.filter(kind=kind).values_list("value", flat=True))
    to_create = [
        UserExclusion(profile=profile, kind=kind, value=v)
        for v in values - existing
    ]
    if to_create:
        UserExclusion.objects.bulk_create(to_create)
