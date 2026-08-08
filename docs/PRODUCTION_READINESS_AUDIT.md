# Production Readiness Audit — Phases 1-18

**Status: AUDIT ONLY. No deployment, no destructive changes, no file edits beyond this document and (per explicit approval) one throwaway read-only GitHub Actions workflow used for database reconciliation.**

Date: 2026-08-08. Scope: full read-only investigation of the repository ahead of a $0/month production migration for real users. Every claim below is grounded in a specific file:line citation or a live command run against the actual local database. Where information came from a web search rather than the code, it is marked as such.

---

## 1. Current architecture (what exists today)

| Layer | Reality today |
|---|---|
| **Frontend** | Next.js 16.2.10 / React 19.2.7, App Router, but **effectively a fully client-rendered SPA** — every page is a trivial server wrapper (`frontend/src/app/*/page.tsx`) around a `'use client'` component tree; no SSR/SSG data fetching found anywhere (zero `generateStaticParams`/`revalidate`/`dynamic` exports). Auth is Django session + CSRF cookies via same-origin relative-path `fetch(..., credentials:'include')` — **zero environment variables are used anywhere in `frontend/src`** (grepped, zero `process.env` hits), zero Next.js API routes, zero middleware. `output:"standalone"` + a custom Docker build — built for the project's own Caddy/Docker self-hosting, not for Vercel. |
| **Backend** | Django 5.2, hand-rolled JSON views (`JsonResponse`) — **no Django REST Framework anywhere** despite that being assumed in the original brief. `gunicorn --workers 2`, no `--timeout` override (30s default). WhiteNoise for static files, no `MEDIA_ROOT` (zero upload features). No CORS package at all — the entire auth model assumes one origin, stitched together by Caddy in the documented Oracle path. `/healthz/` checks DB connectivity only. |
| **Database** | Postgres 16 + pgvector 0.8.4. Local dev DB (live-queried): **15,515 articles, 197 videos, 15,696 embeddings, 4 real users, 251,750 trend rows, 2 trend reports** — see §3. |
| **Pipeline** | SQLAlchemy process in `app/`, orchestrated by `run_pipeline.py` (1,503 lines): scrape → STT-dispatch → embed (skip-if-exists) → digest/enrich → deep-video → cluster → score → trends → RAG-index. |
| **Scheduler** | Celery beat (6 jobs) is the live local/Oracle-path scheduler. **A GitHub Actions replacement (`.github/workflows/pipeline.yml`) already exists**, reproducing all 6 jobs via cron against the same functions directly (no Celery needed) — see §8. |
| **LLM** | Groq exclusively in production (Ollama is a local-dev-only branch), routed through one central function (`app/llm/client_factory.py`) by task tier. **Zero multi-key failover exists today** — see §7. |
| **Email** | Gmail SMTP via App Password, used by both the pipeline's own digest sender and Django's own mail config — same two credentials, two independently-configured env vars. |
| **Redis** | Celery broker + Django cache (rate limiting). Docs already recommend Upstash (two separate free DBs, since Upstash doesn't reliably support multi-DB `SELECT`). |
| **Deployment reality right now** | **Nothing is actually live in the cloud.** `docs/DEPLOYMENT.md` documents two paths (Oracle Cloud VM — blocked earlier this project on ARM capacity; Render fallback — `render.yaml` exists and is well-formed but was never actually deployed). Every service (Postgres, Redis, worker-default, worker-stt, beat, Django, Next.js) is currently running **only because this laptop is on** — native `runserver`/`npm run dev` processes plus a Docker Compose stack, all local. |

---

## 2. Local-only dependencies — what breaks when the laptop is off

**Everything, right now** — there is no live cloud deployment today, so turning this laptop off currently stops the entire product (scraping, ranking, digests, the RAG chat, the web app itself). This is the central fact this whole migration exists to fix.

Specific things that are local-only by design, not just by accident of not-yet-deployed:
- The Docker Compose stack (`db`, `redis`, `worker-default`, `worker-stt`, `beat`) — all containers on this machine.
- Django (`web/`) and Next.js (`frontend/`) dev servers — native processes on `127.0.0.1:8000`/`:3000`.
- The STT worker specifically has a documented reason to *stay* semi-local even after everything else moves: `docs/ROADMAP.md` and the STT worker's own comments flag that `yt-dlp` is more likely to get rate-limited from a datacenter IP than a residential one — this is a real, unsolved tension for the $0 plan, not something GitHub Actions or Render fixes for free.
- The embedding model (`all-MiniLM-L6-v2`, ~90MB) currently benefits from a `worker_process_init` pre-warm hook (`app/celery_app.py:150-172`) that only helps a *persistent* worker process — on GitHub Actions' ephemeral runners, this ~90s load cost is paid once per job run regardless (not a blocker, just a real, unavoidable recurring cost — see §6).

---

## 3. Local vs Neon database status

**Local (docker `ai_news_db`, queried live just now):**

```text
Table                       Local
------------------------------------
articles                    15,515
content_chunks                  77
content_clusters                 8
content_enrichment          14,510
content_scores               15,088
digest_log                     112
embeddings                   15,696
entities                     21,490
saved_items                     57
sources                          16
stt_jobs                        38
taxonomy_topics                  27
trend_reports                     2
trends                      251,750
user_affinities                 317
user_events                   5,395
user_follows                      6
user_interests                   14
user_profiles                     4
user_rankings                   131
user_source_subscriptions         2
users                             4
youtube_videos                  197
```
pgvector: `vector 0.8.4`. Newest article: `2026-08-07 23:23:45+00`. Real users (4): `eng.mohammedeid2024@gmail.com` (pro), `me99804@gmail.com`, `changcountrey@gmail.com`, `mohammedeidabdelmeguid@gmail.com` (all free). Two real trend reports exist — one force-generated (week of Jul 20), **one generated automatically by the new Sunday schedule** (week of Jul 27, `generated_at: 2026-08-02 21:56 UTC`) — live proof the beat/report fix from earlier this session is working, though the ~15-hour delay past the 07:00 UTC trigger is worth a separate look later.

**Neon: STATUS UNKNOWN — reconciliation attempt failed, needs your attention.**

- This machine cannot reach Neon directly (confirmed again just now: `psql` from a local Docker container timed out / "Connection refused" against `ep-fragrant-mouse-...neon.tech:5432` — the same outbound-port-5432 block documented in `docs/DEPLOYMENT.md` from the original migration).
- Per your approval, I pushed a throwaway, **read-only** (`SELECT`/`COUNT` only, no writes) workflow to a new branch (`chore/neon-readonly-check`, commit `a664fd1`) using the same `DATABASE_URL` secret `pipeline.yml` already relies on. It ran automatically on push.
- **The run failed**: [github.com/M0hamed-Eid/ai-news-aggregator/actions/runs/31249013000](https://github.com/M0hamed-Eid/ai-news-aggregator/actions/runs/31249013000). I could not read *why* — downloading the log via the API returned `403: Must have admin rights to Repository`, and I have no GitHub token in this environment to authenticate further.
- **Action needed from you**: open that Actions run and look at the "Query Neon row counts" step's output — it's almost certainly one of: the `DATABASE_URL` repo secret isn't set, is stale, or points somewhere unreachable from GitHub's runners too; or the `apt-get install postgresql-client` step failed. Paste me the error and I'll fix the workflow, or delete the branch/workflow yourself once you've seen it (`git push origin --delete chore/neon-readonly-check`).
- **What we know without live numbers**: the last *verified* Neon snapshot (documented in `docs/DEPLOYMENT.md`'s migration history) matched a local DB of ~3,444 articles. Local has grown to 15,515 since — **over 4x**. Unless something has been actively re-syncing Neon since that original migration (nothing in the codebase does this today — there is no scheduled export/sync job anywhere), **Neon is almost certainly far behind local and should be treated as stale, not as the source of truth, until reconciled.**

**Do not treat Neon as current. Do not migrate/overwrite anything until real counts are confirmed.**

---

## 4. Vercel assessment (frontend)

**Free-tier facts (web search, 2026):** 100GB bandwidth/month, 100K function invocations/month, 10s function timeout, 1M edge requests/month, 6,000 build-minutes/month — **and Hobby is restricted to "personal, non-commercial use"** per Vercel's own terms. [Source: deploywise.dev](https://deploywise.dev/blog/vercel-free-tier-limits-2026), [Source: promptstoproduct.com](https://www.promptstoproduct.com/vercel-free-tier-limits). Worth flagging: an app with real paying (Stripe) users may not cleanly fit "personal, non-commercial" — this is a Vercel ToS question, not a technical one; I'm not qualified to give a legal answer here.

**Code reality:**
- Nothing in the code *technically* blocks a Vercel build — no API routes, no middleware, no `next/image` usage (so no image-optimization quota risk), zero env vars to migrate.
- **The real blocker is cross-origin authentication, and it's architectural, not cosmetic.** The frontend's `fetch()` calls are all bare relative paths (`'/api/session/'`, `'/behavior/save/'`, etc. — `frontend/src/lib/api.ts:94,113,117`) with `credentials:'include'`, and the code's own comment states plainly: *"same-origin only... no CORS handling belongs here"* (`frontend/src/lib/api.ts:7-8`). Django has **no CORS package configured at all** (`web/config/settings/prod.py:36-42`), and neither `SESSION_COOKIE_SAMESITE` nor `CSRF_COOKIE_SAMESITE` is set anywhere (defaults to `Lax`). Put a Vercel-hosted frontend on one domain and a Render-hosted Django on another, and: the relative fetches resolve against the wrong domain, and even fixed, the browser would block the credentialed cross-site cookie flow without `django-cors-headers` + `SameSite=None; Secure` cookies on the Django side.

**Verdict: technically buildable, but not deployable as a working product without real auth-architecture changes on both sides first (§10 has the concrete list).** This is the single biggest piece of new work in this whole migration, bigger than anything about hosting tiers.

---

## 5. Render assessment (backend)

**Free-tier facts (web search, 2026):** 750 instance-hours/month/workspace (enough for one always-running service, since spun-down time doesn't count), spins down after 15 minutes idle, ~1 minute cold start on wake. [Source: unanswered.io](https://unanswered.io/guide/render-free-tier-details), [Source: render.com/docs/free](https://render.com/docs/free).

**Code reality — mostly ready, with real gaps:**
- `render.yaml` already exists, targets `web/Dockerfile`, `healthCheckPath: /healthz/` — a solid starting point, already built in an earlier phase of this project.
- **Gap — silent `ALLOWED_HOSTS` failure mode**: `prod.py` never overrides it, so if the `DJANGO_ALLOWED_HOSTS` Render env var (marked `sync: false`, i.e. manual-entry-required) is ever left blank, the app falls back to `["127.0.0.1","localhost"]` and 400s every real request — a silent, non-obvious failure rather than a loud startup error.
- **Gap — the SSE chat endpoint has no safe home on Render.** In the Oracle/Docker path, `/assistant/stream/` deliberately runs on its own ASGI (`uvicorn`) process specifically so one open chat stream can't pin one of only 2 gunicorn sync workers and cap the whole site's concurrency at "1 other visitor" (`docker/docker-compose.prod.yml:80-98`'s own comment says this explicitly). `render.yaml` defines exactly one service — no such isolation exists there. This is a real capacity risk for a single-service Render deploy, not a theoretical one.
- **Gap — the Redis-backed rate limiter has no exception handling.** `web/apps/behavior/ratelimit.py:59-66` and its two callers (save/hide/events, and the assistant's burst/daily gates) will 500 rather than degrade gracefully if Upstash is briefly unreachable — inconsistent with how the rest of the app (search, source submission) degrades gracefully on failure.
- `docs/DEPLOYMENT.md`'s own production-URL table is stale — it still says "Public REST API is out of scope," which no longer matches the real `/api/*` surface built for the Next.js frontend.

**Verdict: workable for $0, but needs the ALLOWED_HOSTS safety default, a decision on the chat-streaming risk (accept it, or find a free 2nd process), and the rate-limiter try/except — before real users depend on it.**

---

## 6. Embedding strategy

**Model**: `all-MiniLM-L6-v2` (sentence-transformers 5.6.0), 384 dimensions, ~90MB, **CPU-only, no GPU needed** — legitimately runnable on a GitHub Actions ephemeral runner (`app/embeddings/embedding_service.py:17,20-28`).

**Idempotency — confirmed genuinely good, this is the single most important finding of this section:**
- Every new-content embedding is gated by a real `exists_for(content_type, content_id)` check *before* generating anything (`run_pipeline.py:560-601`, `app/database/repositories/embedding_repository.py:20-25`).
- Even under a race (e.g. two overlapping pipeline runs), duplication is structurally impossible: `EmbeddingRepository.upsert()` is a Postgres `INSERT ... ON CONFLICT DO UPDATE`, backed by a hard `UniqueConstraint(content_type, content_id)` on the table itself.
- Re-embedding of *existing* content only happens deliberately, in exactly two cases: (a) an item's very first enrichment pass (`get_unenriched()` — a `NOT IN` filter that permanently excludes already-enriched rows), or (b) the M12 "deep video" second pass for long videos, which is itself gated by `has_chunks()`. It is **never** unconditional on every run.
- Same protection extends to `content_chunks` (M12 chapters) and `rag_chunks` (M14 RAG index) — both delete-then-insert per item, both version/existence-gated.
- **Direct answer to the "did the earlier 90-minute pipeline-loop bug create duplicate embeddings" question: no.** Traced through the actual code — the exists-check + unique constraint + upsert pattern would have wasted redundant compute during that bug, but could not have produced duplicate rows in `embeddings`, `content_chunks`, or `rag_chunks`. No cleanup needed there.
- One real scale caveat: `run_embedding_phase` only scans the newest **1,000** articles/videos per run (`limit=1000`) — fine today, worth remembering if daily new-item volume ever exceeds that between runs.

**Recommendation: Option A — keep the existing model, run it on GitHub Actions.** There is no technical reason found in this audit to swap models. The only GH-Actions-specific cost is paying the ~90s model download+load once per ephemeral job (no persistent process to pre-warm) — a wash against the cold-start problem that already existed locally, not a new one.

---

## 7. Groq multi-key strategy

**Current state — confirmed zero multi-key logic anywhere.** Exactly one `GROQ_API_KEY` env var, read in two independently-configured places (`app/llm/client_factory.py:56` for the pipeline, `web/config/settings/base.py:183`/`web/apps/assistant/llm_client.py:43` for Django's own direct SSE-streaming client — the one place that bypasses `client_factory.py` entirely).

**7 real LLM call sites found**, 6 of 7 already have decent-to-good rate-limit-aware exponential backoff and fully isolate failures per-item (a bad article/video/chunk never aborts the rest of a batch — confirmed by tracing the calling loops, not just the agent's own docstrings). **The 7th — `web/apps/assistant/llm_client.py:44`, the RAG chat's streaming path — has zero retry/backoff/exception handling at all.** This is a real, independent gap worth fixing regardless of the multi-key work, since it's the one user-facing path with no safety net.

**Design for multi-key failover** (not yet implemented — audit only): the natural integration point is `app/llm/client_factory.py` (already the single routing chokepoint) plus the one Django-side exception. A "Groq Key Manager" should:
- Read `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, ... from env vars (never hardcoded), try them in order.
- Catch rate-limit/quota errors specifically (matching the existing `GroqRateLimitError`/`OpenAIRateLimitError` pattern already used in every agent), not blanket exceptions.
- Cap **total** attempts across all keys, not per-key — the existing agents already retry up to 4x each with exponential backoff; naively multiplying that by N keys risks a very long worst-case wall-clock delay for one request. Needs a shared budget.
- Never log key values (confirmed: no call site currently logs the key itself — good baseline to preserve).
- Fix `llm_client.py`'s complete lack of error handling as part of this same change, since it's the one place a Groq failure currently has no fallback at all.

---

## 8. Scheduler strategy

**Task classification** (every `@celery_app.task` in the repo, traced to its real caller):

| Classification | Tasks |
|---|---|
| **Interactive/user-facing — needs a persistent "interactive" worker** | `search_tasks.embed_query_task` (5s timeout, degrades to keyword search on failure), `source_submission_tasks.*` (20s/25s timeouts, degrades to an error message), `rag_tasks.rag_answer_task`/`rag_retrieve_task` (25s/15s timeouts) |
| **Batch/schedulable — GitHub Actions can run these directly today** | `pipeline_tasks.run_full_pipeline_task` (the 6-hourly full pipeline), `affinity_tasks.aggregate_affinities_task`, `profile_vector_tasks.compute_profile_vectors_task`, `ranking_tasks.rank_all_users_task`, `source_revalidation_tasks.revalidate_user_sources_task`, `trend_tasks.generate_weekly_trend_report_task` |
| **Needs its own worker, but not user-facing** | `stt_tasks.transcribe_video_task` — fired fire-and-forget from inside the pipeline (not from any HTTP request), but needs dedicated CPU and, per existing project docs, ideally a non-datacenter IP for `yt-dlp`. Already documented as **not** well-covered by the GitHub Actions fallback path (jobs queue but nothing consumes them there). |

**The GitHub Actions replacement already exists and mostly works**: `.github/workflows/pipeline.yml` reproduces all 6 batch jobs on matching cron schedules, calling the exact same underlying functions directly (no Celery needed for these) via `app/scripts/run_scheduled_job.py`. Requires repo secrets: `DATABASE_URL`, `REDIS_URL`, `GROQ_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`.

**One concrete bug found**: `pipeline.yml:32`'s trend-report cron is still `"0 6 * * 1"` (Monday 06:00 UTC) — **stale** against the Sunday 07:00 UTC schedule fixed in `app/celery_app.py` earlier this session. These need to move together or the two paths will diverge on which week gets reported.

**Recommendation**: keep Celery+Redis for local dev (already working, no reason to remove), use GitHub Actions for the 6 batch jobs in production (mostly already built), and make an explicit decision about the 3 interactive tasks + STT before launch — either accept their documented graceful-degradation behavior on a Celery-less production path, or budget for a small always-on interactive worker somewhere.

---

## 9. Other free-tier alternatives (service by service)

| Service | Current | Free tier reality (2026) | Recommendation |
|---|---|---|---|
| Frontend hosting | Vercel (not yet deployed) | Hobby: 100GB bw, 100K invocations, 10s fn timeout, personal-use restriction ([source](https://deploywise.dev/blog/vercel-free-tier-limits-2026)) | Viable once cross-origin auth is fixed (§4) |
| Backend hosting | Render (not yet deployed) | 750 free instance-hrs/mo, 15-min spin-down ([source](https://render.com/docs/free)) | Viable with the gaps in §5 addressed |
| Database | Neon | Already in use; reconciliation pending (§3) | Keep — no reason found to change |
| Redis | Not yet provisioned in prod | Upstash: 256MB, 500K commands/month ([source](https://agentdeals.dev/vendor/upstash)) | Matches existing docs' recommendation (2 separate DBs) |
| LLM | Groq only | Groq: ~30 RPM / 6K TPM free for Llama 3.3 70B. Alternatives: **Cerebras** (1M tokens/day free, fastest throughput), **Google Gemini Flash** (1,500 req/day, no card, no expiry), **Mistral** (1B tokens/month, all models) ([sources](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/), [wetheflywheel.com](https://wetheflywheel.com/en/ai-model-access/free-llm-api-tiers-2026/)) | Groq multi-key first (§7); Gemini Flash or Cerebras as a genuine cross-provider fallback tier is worth a follow-up design, not urgent for launch |
| Embeddings | Local sentence-transformers | N/A — self-hosted, free by nature | Keep as-is (§6) |
| Email | Gmail SMTP (App Password) | Works today, no rate-limit handling found in the reachable code. Alternatives if Gmail becomes unreliable at volume: **Brevo** (300/day ≈ 9,000/mo free, full API) or **Resend** (3,000/mo, 100/day) ([sources](https://www.brevo.com/blog/best-email-api/), search results) | Gmail is fine at current volume (4 users); revisit only if digest volume grows meaningfully |
| Scheduler | Celery beat (local) | GitHub Actions: 2,000 min/mo free for **private** repos, unlimited for public repos | Already built (§8); this repo is public (confirmed), so Actions minutes are effectively unlimited |
| Object storage | None used | N/A | Not needed — confirmed zero file-upload features anywhere |
| Monitoring | None | See §18 (lightweight, no paid infra) | `/healthz/` + GH Actions logs is the realistic $0 baseline |
| Authentication | Django's own (session + password) | N/A — self-hosted | Keep — no third-party auth provider in use or needed |
| Analytics | None (confirmed via grep — zero third-party analytics/tracking scripts anywhere, frontend or backend) | N/A | Nothing to migrate; also directly relevant to the Privacy Policy (§11) |

---

## 10. Current security gaps

**What's solid (verified directly, not assumed):**
- No hardcoded secrets anywhere in `web/` or `app/` — every sensitive setting goes through `env(...)`. `.env*` files are correctly gitignored and confirmed absent from git history (`git ls-files` shows only `.env.example` variants tracked).
- Login rate limiting (`login_rate_limit_ok`) is genuinely wired into **both** the template login view and the JSON API login view — not defined-but-unused.
- Stripe webhook signature verification is real: `stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)`, explicitly rejects if the secret is unset (`web/apps/accounts/billing.py:169-179`).
- The staff-only Ops dashboard genuinely checks `request.user.is_staff` server-side (both the legacy view and the API view), returning 403 otherwise — not just hidden from navigation.
- **IDOR sweep of every user-owned-data endpoint I checked** (save/hide toggle, follow/unfollow, interests, sources, wizard state, digest settings) — every single one scopes its query/mutation to `request.user` (or `request.user.profile`). None trust a client-supplied user id for anything. No IDOR found in what was checked.
- `EventIngestView` is CSRF-exempt (`web/apps/behavior/views.py:28`), which sounds alarming out of context — but it's justified (`navigator.sendBeacon` physically cannot carry a CSRF token) and mitigated by requiring authentication, an Origin/Referer first-party check, and per-user rate limiting. Not a real vulnerability.

**Real gaps found:**
- `web/apps/behavior/ratelimit.py`'s Redis calls have no exception handling — an Upstash hiccup 500s several endpoints instead of degrading.
- `ALLOWED_HOSTS` silently defaults to localhost-only if the Render env var is forgotten (§5).
- `web/apps/assistant/llm_client.py`'s streaming Groq call has zero error handling (§7).
- `SESSION_COOKIE_SAMESITE`/`CSRF_COOKIE_SAMESITE` are unset (default `Lax`) — fine today, will need to become an explicit `None`/`Secure` decision the moment a cross-origin frontend exists (§4).
- **Honest scope caveat**: a dedicated security-review agent I spawned for this audit hit a usage limit partway through and didn't finish. I completed the highest-value parts myself directly (the IDOR sweep above, CORS/CSRF/session settings, Stripe webhook, staff gating) — but this was not a line-by-line re-check of literally every view in the app the way that agent would have done. What's here is solid, not exhaustive.

---

## 11. Privacy / data-collection inventory

Built from actual model fields, not assumption. **Confirmed via repo-wide grep: no IP address, User-Agent, or device-fingerprint capture exists anywhere in this codebase, and no third-party analytics/tracking script exists anywhere (frontend or backend).**

| Data | Where stored | Why collected | Required or optional |
|---|---|---|---|
| Email | `users.email` | Account identity, login | Required |
| First/last name | `users.first_name/last_name` | Personalization (display name) | Optional (blank-able) |
| Password (hashed) | Django's default hasher (PBKDF2), never plaintext | Auth | Required |
| Plan/billing status | `users.plan`, `stripe_customers.*` (Stripe IDs + status only — **no card numbers ever touch this app**, Stripe handles those directly) | Entitlements | Required for Pro features |
| Persona, bio | `user_profiles.persona/bio` | Onboarding personalization | Optional |
| Interests, exclusions, source subscriptions, follows | `user_interests`, `user_exclusions`, `user_source_subscriptions`, `user_follows` | Feed personalization | Optional |
| Saved / read / hidden state | `saved_items` (+timestamps) | Core product feature (Library) | Necessary for the feature |
| Behavioral events | `user_events`: `event_type` (impression/click/dwell/scroll/save/hide/search/digest_click), `content_type`/`content_id`, a numeric `value` (dwell ms or scroll %, depending on type), `created_at` | Personalized ranking | Necessary for the feature; **90-day auto-deletion confirmed real** (`web/apps/behavior/management/commands/prune_old_events.py`) |
| Digest settings | `user_digest_settings` | Email preferences | Optional |
| Digest send log | `digest_log` (which user, when sent — no email *content* stored) | Lets the profile page show "digests received: N" | Derived/necessary |
| Computed affinities | `user_affinities`, `user_rankings` | Derived from events, not directly entered | Necessary for the feature, not separately "collected" |
| **Not collected** | — | — | IP address, User-Agent/device fingerprint, any cookie beyond Django's own session+CSRF cookie, any third-party analytics |

This inventory is what a Privacy Policy must be written from — no more, no less.

---

## 12. Terms of Use — requirements (not yet drafted)

None exists today (confirmed via repo-wide grep — zero hits for "terms"/"privacy"/"consent" anywhere in `web/` or `frontend/`). Given real users and a paid tier, a Terms of Use page is warranted. It should cover, grounded in what the app actually does: acceptable use, account responsibility (the app requires a password — no third-party login exists to shift responsibility to), that content is aggregated from third-party sources (with links preserved — confirmed every article/video always carries its source URL), that summaries and recommendations are AI-generated and may contain errors, free-tier limitations (matches the real `FEATURE_PLANS` gates already in `web/apps/accounts/entitlements.py`), service availability (honest: this is a $0 hobby-tier deployment, not an SLA-backed service), and account suspension/termination. **Governing law/jurisdiction should be flagged for your own legal review, not invented** — I'm not qualified to assert Egyptian or any other jurisdiction's specifics.

## 13. Privacy Policy — requirements (not yet drafted)

Must be written directly from §11's inventory — nothing more, nothing less. Needs to name the real third-party processors that actually touch data (§16 below), state the confirmed 90-day event retention, and be explicit that no IP/device/analytics data is collected (a true, checkable claim per this audit).

## 14. Consent requirements

- **Required, single checkbox**: acceptance of Terms of Use at signup (the account cannot function without agreeing to how the service works).
- **NOT everything belongs behind that one checkbox.** Digest emails are opt-in-by-default today via onboarding (a `user_digest_settings` row is created for every user, not a separate marketing consent) — worth deciding whether that default itself needs a visible toggle at signup rather than being silently on. This needs your input on intent (is the weekly digest core product, or optional marketing?) before I design the exact consent UI — it changes the answer.
- No optional/marketing-only data processing was found in the codebase beyond the digest question above — there's no separate "marketing emails" feature to gate.

## 15. User deletion / data-rights requirements

**No self-service account deletion exists today** (confirmed via grep — zero delete-account code in `web/apps/accounts`). Given real users, this needs to exist in some form before/soon after launch — even a manual, staff-mediated process is better than nothing, but a real endpoint is the right target. Design constraint already clear from the schema: `saved_items`/`user_events`/etc. all `on_delete=models.CASCADE` from `User` (confirmed in `web/apps/behavior/models.py`), so deleting a `User` row already correctly cascades to *only that user's* data — but **shared content (articles, videos, sources) is pipeline-owned in a completely separate database/ORM and is never touched by a Django-side user delete**, matching the requirement that deleting one user must never remove shared catalog content.

---

## 16. Concrete implementation plan (for your review — not started)

1. **Fix the Neon reconciliation** (§3) — get the throwaway workflow working, get real numbers, decide sync-vs-fresh-migrate.
2. **Cross-origin auth work** (§4) — the single biggest piece of new work: add `django-cors-headers` scoped to the real Vercel domain, decide on `SameSite=None; Secure` cookies, give the frontend a real configurable API base URL.
3. **Render hardening** (§5) — safe `ALLOWED_HOSTS` default, decide the SSE-chat concurrency risk, wrap the rate-limiter in a try/except.
4. **Sync the two scheduler paths** (§8) — fix `pipeline.yml`'s stale trend-report cron.
5. **Groq multi-key failover + fix `llm_client.py`'s missing error handling** (§7).
6. **Terms of Use + Privacy Policy pages**, drafted from §11/§12/§13, flagged for your legal review before publishing.
7. **Consent UI** at signup, pending your call on the digest-opt-in question (§14).
8. **Account deletion endpoint** (§15).
9. Only after all of the above: actual deployment (Phase 19 in your original request).

**I have not made any destructive or deployment changes. Per your instructions, I'm stopping here and waiting for your review and approval before proceeding to any of the above.**
