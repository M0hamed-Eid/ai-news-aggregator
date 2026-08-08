# apps/accounts/legal.py
#
# Single source of truth for the currently-effective Terms of Use / Privacy
# Policy versions (M16). Bump these when either document materially
# changes — every logged-in user whose latest TermsAcceptance.terms_version
# no longer matches CURRENT_TERMS_VERSION gets needsTermsAcceptance=True in
# their session payload (see api_views._session_payload), which the
# frontend uses to prompt re-acceptance. A wording typo fix does not need a
# version bump; a change to what the service actually does/collects does.
#
# Format is a plain date string, not semver — simplest thing that's still
# monotonically comparable and human-readable in an admin/audit context.
CURRENT_TERMS_VERSION = "2026-08-08"
CURRENT_PRIVACY_VERSION = "2026-08-08"
