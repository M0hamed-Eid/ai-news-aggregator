# Future: Automated Daily Marketing Post — Architecture Proposal

**Status: design only, not implemented.** No code, dependencies, credentials, or platform apps
have been created for this. This document exists so the shape is agreed on before any of it is
built, and so it's built by extending patterns this codebase already has, not inventing new ones.

## Context

Once a dedicated Gmail account, LinkedIn/X/Facebook pages exist, the goal is one automated daily
post summarizing interesting AI news, sourced from AI Compass's own corpus. This proposal reuses
three things this codebase already does well rather than designing from scratch:

1. **The digest pipeline's shape** — generate once, fan out to many recipients (here: platforms
   instead of email addresses).
2. **The weekly trend narrative's grounding discipline** (`app/agents/trend_narrative_agent.py`)
   — every factual claim must resolve to a real corpus item via a handle-based citation
   (`[S1]`, `[S2]`...) that's mechanically validated server-side; anything ungrounded is dropped
   before it's ever rendered. A public marketing post carries real reputational risk if it
   states something false — this exact mechanism is the reason to reuse it, not a nice-to-have.
3. **The M6/M9-established "Django is a Celery client, the pipeline does the real work"
   boundary** — Django owns platform credentials and scheduling UI; the pipeline (which already
   has the LLM stack, the content-scoring data, and Celery beat) generates and grounds the post.

## Pipeline shape

```
[Candidate selection]  →  [ONE LLM draft]  →  [mechanical grounding filter]
        ↓
[store as marketing_posts row, status=draft]
        ↓
(optional) [human approve/edit/skip]
        ↓
[N platform adapters — each formats + publishes independently]
        ↓
[update row: published_at, per-platform post ids/urls]
```

This is the digest pipeline's "generate once, fan out to N" shape and the trend narrative's
"generate once, grounded, render to multiple surfaces" shape, applied to a third case. Reusing
the shape means reusing the reviewer's mental model, not just code.

### 1. Candidate selection — reuse existing signals, no new "interestingness" model

Pull from data structures that already exist and are already computed daily/continuously:
- Top-scored recent items from `content_scores` (M8's quality-scoring phase — already runs
  corpus-wide every pipeline run).
- Today's burst-detected trending topics/entities from `trends` (M11 — the exact same table
  Home's Trending module and the weekly narrative already read).
- Hot clusters (`ContentClusterMember` cluster-size velocity — the same query behind
  `get_hot_clusters()`, extended in this batch of work to power the new Story Clusters tab).

No new scoring/ranking logic — this is a read over three tables the pipeline already maintains.

### 2. Content generation — one LLM call, grounded

New `app/agents/marketing_post_agent.py`, structurally identical to
`trend_narrative_agent.py`: strict-Pydantic output with pre-construction coercion (the same
"don't let one bad enum field kill the whole call" discipline from `enrichment_agent.py`,
documented in `.wolf/cerebrum.md`'s llm-001 entry), handle-based citations resolved server-side,
any claim whose citation doesn't resolve to a real, actually-scored/trending item is dropped
before the post is ever built. Output: one headline, a 2-3 sentence body, a primary link back to
the relevant AI Compass page, and suggested hashtags/topics.

One LLM call per day total — not one per platform. Per-platform differences (character limits,
hashtag conventions, image aspect ratio) are handled by cheap, non-LLM formatting in step 4.

### 3. Approval workflow — recommend defaulting to "on," unlike the trend narrative

The trend narrative auto-publishes with no review gate — that's the right call for an internal
report to signed-in Pro users. A public post to the brand's real LinkedIn/X/Facebook accounts is
a different risk profile: it's public, harder to unsend, and reputationally binds the brand.
**Recommendation: default to a review step**, at least initially — a small staff-only page
(mirroring `OpsDashboardView`'s existing `is_staff`-gated pattern) showing today's draft
(headline, body, chosen image) with Approve / Edit / Skip. A single settings flag can later flip
this to fully autonomous once there's a track record, without changing anything upstream — this
is a genuine tradeoff (reputational risk vs. daily friction) worth deciding explicitly rather
than silently inheriting the trend narrative's auto-publish precedent.

### 4. Platform integrations — one thin adapter per platform, independently feature-flagged

New Django app `apps.marketing` (Django owns credentials/OAuth, matching the ownership boundary
already used for Stripe in M13 — `apps.accounts.billing`). A `SocialAccount` model stores
encrypted OAuth tokens per platform, refreshed via each platform's own standard flow. A common
adapter interface:

```
publish(text: str, image_url: str | None, link: str) -> PostResult
```

with one implementation each for LinkedIn, X (Twitter API v2), and Facebook (Graph API). Each
adapter is independently feature-flagged — an unconnected platform is simply skipped, mirroring
the existing `stripe_configured()` graceful-degradation pattern from `billing.py` (upsell UI
disables itself when Stripe env vars are absent, rather than erroring).

**Images**: reuse the source-artwork/branding system built in this same batch of work
(`docs/branding/`) — a post's image is the real content item's thumbnail when one exists,
otherwise the app's own social-share-image asset (see `APP_BRANDING_PROMPTS.md`) as a fallback,
exactly mirroring the digest email's `image_url`-then-branded-fallback pattern in
`email_template.py`.

### 5. Scheduling

New Celery beat entry (`app/celery_app.py`'s existing beat schedule already has this exact
shape for the 6-hourly pipeline run and the weekly Monday trend-narrative job — one more entry,
not a new scheduling mechanism). Runs once daily, shortly after the day's last scoring/enrichment
pass so `content_scores`/`trends` are fresh — mirroring the trend narrative's "reports on the
just-completed period" timing discipline.

**Idempotency**: a new pipeline-owned `marketing_posts` table gets a draft row written *before*
any platform publish is attempted, with a same-day uniqueness check — a re-triggered task (e.g. a
Celery retry) checks "does today already have a row?" first, exactly like the digest pipeline
already guards against double-sending via `digest_log`.

Recommended queue: the existing `default` queue, not a new dedicated one — this is one LLM call
and a handful of small HTTP posts per day, nothing like STT's CPU-bound profile that justified a
dedicated `stt` queue.

### 6. Reusable pipeline / future scalability

- **Multiple posts/day**: the same daily task, run more than once with a different `hours`
  time-slice — every phase function in this codebase already takes an `hours` parameter, so nothing
  new is needed for a "morning + evening" cadence later.
- **Engagement feedback loop**: a new `marketing_post_metrics` table (likes/shares/clicks pulled
  from each platform's own API) could, much later, feed back into candidate selection — this is
  explicitly a v2+ idea, not required for a working v1, and shouldn't gate shipping the first
  version.
- **Multiple brand voices/accounts**: `SocialAccount` already models N accounts per platform if
  that's ever needed — no redesign required to add a second brand identity later.

## Explicitly out of scope for this proposal

No code, no new pip/npm dependencies, no platform developer-app registration, no credential
handling, no Gmail/social account setup. This is a design to review and adjust before any of that
starts.
