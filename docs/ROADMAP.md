# AI Compass — Architecture & Product Roadmap

> **Status:** Living document. This is the single source of truth for where the project is going and *why*.
> **Last updated:** 2026-07-14
> **Horizon:** ~6–9 months of solo-developer, milestone-by-milestone work (M6 → M13).
> **Audience:** the developer, and any future AI assistant session. Read this before proposing architecture. If a proposal contradicts the **Architecture Principles** below, the principles win unless this document is explicitly amended.

---

## 0. How to use this document

1. **Architecture Principles** are hard rules. Do not break them without amending this section and recording why in the Decision Log at the bottom.
2. **Milestones (M6–M13)** are the ordered plan. Each feature inside a milestone is tagged **[Core]**, **[Nice-to-have]**, **[Pro]**, or **[Research]** — build Core first, defer the rest without guilt.
3. **Parking Lot** lists ideas we deliberately rejected or postponed, with reasons. Before re-proposing any of them, read why they're parked. This section exists to stop us re-litigating settled decisions.
4. Complexity is sized for **one developer**: **S** ≈ a few days, **M** ≈ 1–2 weeks, **L** ≈ 3–5 weeks.

---

## 1. Where the project is today (current state)

**Product:** AI Compass — a working multi-user AI-news platform.

**Two-process, shared-database architecture:**

- **Pipeline (`app/`, SQLAlchemy, Python 3.11):** scrapes 9 sources, summarizes + ranks with Groq LLMs, embeds content, generates and emails per-user digests. Run via `run_pipeline.py` (cron-style, single process).
- **Web (`web/`, Django 5.2.16, Python 3.11):** public home, personalized `/feed`, profile, preferences, source management, skippable onboarding, article/video detail. Reads pipeline tables; writes only its own.
- **Database:** one PostgreSQL (`127.0.0.1:5433/ai_news`), `pgvector` enabled.

**Key existing assets the roadmap builds on:**

| Asset | Detail | Why it matters |
|---|---|---|
| Embeddings | `all-MiniLM-L6-v2`, 384-dim, in a pgvector `Vector(384)` column, **with `model_name` stored per row** | Recommender + semantic search are mostly *reuse*, not new work. Model-version is already tracked. |
| Source Registry | DB-driven `sources` table (key/category/adapter_type/handler/config JSONB) | User-defined sources become a data change, not a code change. |
| Generic RSS adapter | `RssFeedScraper` is config-driven | New RSS/Atom source = one registry row. |
| Ranking persistence | `user_rankings` table written by the pipeline, read by Django | The "compute in batch, read on web" pattern is proven. |
| LLM abstraction | `client_factory` → Groq (`llama-3.3-70b` / `3.1-8b`) with **Ollama local fallback** | Bulk/backfill LLM work has a zero-marginal-cost escape hatch. |
| Cross-ORM read mirrors | `catalog` (Django reads pipeline tables) + `django_readmodels.py` (pipeline reads Django tables) | The ownership boundary is already enforced and documented. |

**The one fact that shapes the entire roadmap:** we have **no user-interaction data** (no clicks, dwell, saves, or CTR). Every "smart" system on the wishlist — quality scoring, recommendation, behavioral learning — is either untrainable or a disguised heuristic until that data exists and accumulates. This is why instrumentation comes before intelligence.

---

## 2. Architecture Principles (do not break)

These are invariants. They've been earned through the project's history (see `.wolf/cerebrum.md`) and they keep the system coherent as it grows.

1. **Ingest once, personalize later.** Content is scraped, summarized, embedded, scored, and clustered exactly once — globally. Per-user work (ranking, filtering, digest assembly) happens at read/serve time over that shared pool. Never scrape or enrich per-user.
2. **Django owns user-facing tables. SQLAlchemy owns pipeline tables.** Each ORM `CREATE`s, migrates, and writes **only** its own tables. Ownership of every new table is decided explicitly and recorded in this doc.
3. **Cross-ORM communication is read-only.** Django reads pipeline data via `managed=False` mirrors; the pipeline reads Django data via read-only mirror models. Neither writes across the boundary. When a feature seems to need a cross-ORM write, the answer is *always* "add a table on the writer's own side and let the other side read it" — never "just this once." (This rule has already caught one real violation; see `digest_log`.)
4. **One enrichment call per content item.** Summary, taxonomy, entities, content-type, technical depth, and "why this matters" are produced in a **single** structured LLM call at ingest time. Adding a metadata field means extending that call's JSON schema, not adding a new pass over the corpus.
5. **Structured metadata over repeated LLM calls.** Prefer a stored, queryable attribute computed once over an LLM call made repeatedly at read time. LLM calls are for generation, not for facts we can persist.
6. **Recommendation trends toward deterministic and less LLM-dependent.** Over time the LLM's role in ranking shrinks to generating human-readable *explanations*. Scoring itself moves from heuristic → learned-tabular (gradient boosting) using our own logged features. We do not put an LLM in the hot path of ranking.
7. **Log features now so they become future ML training data.** Any scoring or ranking decision logs its input feature vector, not just its output. Interaction events are captured from day one of instrumentation. Data not captured is lost forever; capture is cheap, retraining on absent history is impossible.
8. **Capture raw, serve aggregated.** High-volume signals (events, impressions, full transcripts) are captured raw, then reduced to compact derived tables (affinities, scores, summaries) that the serving path reads. Raw high-volume data is pruned on a retention schedule.
9. **Store the model/version alongside derived artifacts.** Embeddings, scores, and any learned output record which model/prompt version produced them, so a model swap invalidates cleanly instead of silently corrupting similarity math. (Embeddings already do this; extend the discipline everywhere.)
10. **Every user-facing knob maps to a ranking feature or a filter.** A preference that nothing in the system acts on is UI debt. If we can't name the ranker input or query it drives, we don't add it.
11. **Schema changes go through migrations.** Once Alembic lands (M6), no more hand-written `ALTER TABLE` against the live DB. Django side uses Django migrations. Both are committed artifacts.
12. **Entitlements are designed in from the start; billing is integrated last.** Feature gates check a `plan` attribute throughout M6–M12. Payment integration (Stripe) is deferred to M13 — gating logic is cheap inline and painful to retrofit; billing code is worthless without traffic.

---

## 3. Milestone map (at a glance)

| # | Name | Complexity | Core theme | Portfolio impact |
|---|---|---|---|---|
| **M6** | Infrastructure Foundation | M | Alembic, Redis, Celery, job queue | Low (enabling) |
| **M7** | Behavioral Instrumentation & Saves | M | Events, saves, read-state, aggregation, transcript capture | Medium |
| **M8** | Content Intelligence Layer | L | Enrichment call, taxonomy, entities, clustering, quality score v1 | High |
| **M9** | Owned Recommender + Preferences v2 + Search | L | Two-stage retrieval, MMR, profile vectors, eval harness | **Highest (centerpiece)** |
| **M10** | User Sources & People Following | M | Registry extension, AI-relevance gate, entity follows, alerts | High |
| **M11** | Insights & Trending | M–L | Burst detection, entity pages, narratives | **Highest (product identity)** |
| **M12** | Deep Media | M | Long-video hierarchical summarization, STT, podcast | Medium–High (demo) |
| **M13** | SaaS Hardening & Monetization | M | Auth hardening, Stripe, dashboards, API, ops | Low novelty, mandatory |

**Reconciliation note:** an earlier draft used M6–M12 with M6 = "Behavioral Foundation & Infrastructure." That single milestone bundled risky new infra (Alembic/Redis/Celery) with product instrumentation (events/saves) into ~5 weeks of mixed-concern work — the mega-milestone anti-pattern. It's now split into **M6 (Infrastructure)** and **M7 (Instrumentation)**; everything downstream shifts by one. Old→new mapping: old-M7 Content Intelligence → **M8**, old-M8 Recommender → **M9**, old-M9 User Sources → **M10**, old-M10 Insights → **M11**, old-M11 Deep Media → **M12**, old-M12 Monetization → **M13**.

---

## 4. Milestones in detail

---

### M6 — Infrastructure Foundation

**Objective.** Put the plumbing in place that every later milestone assumes exists: real migrations, a job queue, and an entitlement scaffold. Ship nothing user-visible; make everything after this safe to build.

**Why now.** This is the counterintuitive-but-correct first step. The project has been surviving on `create_all()` + hand-written `ALTER TABLE` against the live DB (documented pain in the project history). The roadmap ahead is the heaviest schema-churn phase in the project's life — doing that without migration tooling is negligent. Likewise, M7+ features (aggregation jobs, on-demand summaries, STT, TTS, ranking refresh) all need background execution the current single-process cron pipeline can't provide. Build the foundation before the house.

**Dependencies.** None. Deliberately.

**Database changes.**
- Adopt **Alembic** for the pipeline (`app/`): baseline a migration against the *current* schema, then all future pipeline DDL is a migration. **[Core]**
- `plan` field on the Django user (`free` default) + a nullable `plan_expires_at`. **[Core]**
- No other schema yet — this milestone is about *how* schema changes, not new tables.

**Backend changes.**
- Introduce **Celery** (or RQ; Celery preferred for scheduling maturity) with **Redis** as broker/result backend. **[Core]**
- Port the existing `run_pipeline.py` phases to enqueue-able tasks (keep the CLI entry for manual runs; add scheduled beat entries). **[Core]**
- A thin `entitlements.py` helper: `user_can(user, feature)` reading `plan`. Used nowhere yet, ready for everywhere. **[Core]**

**Frontend changes.** None (a hidden "you're on Free" note at most). 

**ML/AI components.** None.

**Infrastructure requirements.** Redis (local container now, managed instance at deploy). A Celery worker process + beat scheduler added to the run topology. Alembic in the pipeline's dependency set. Document the new process diagram in the repo README.

**Complexity.** **M.** Mechanical but touches deployment topology and requires careful Alembic baselining of an existing DB.

**Portfolio impact.** **Low** directly, but "migrations + task queue + entitlement layer" is exactly the infrastructure competence a SaaS reviewer checks for. Its absence is more noticeable than its presence.

**Risks.**
- *Alembic baselining an existing DB* is the classic footgun — the first migration must `--autogenerate` against reality and be reviewed line-by-line, then stamped, or it'll try to recreate existing tables. Mitigate: baseline, `alembic stamp head`, verify with a no-op autogenerate.
- Celery + Windows dev environment has known quirks (prefork pool). Mitigate: use `--pool=solo` locally, document it.

**Success criteria.**
- A schema change can be made by writing + running a migration, with zero hand-written SQL.
- A trivial task (`enqueue a log line`) runs on a Celery worker via Redis and returns a result.
- `user_can(user, "anything")` resolves against `plan` in a shell test.
- Existing pipeline still runs end-to-end via both the CLI and a scheduled task.

---

### M7 — Behavioral Instrumentation & Saves

**Objective.** Start the data flywheel. Capture what users do, give them saves/read-state, and stand up the nightly aggregation that turns raw events into per-user affinities. Also stop discarding data we'll want later (full transcripts).

**Why now.** Interaction data compounds with **calendar time and nothing else**. Every week without capture is a week of training data that never exists. This is the single highest-leverage non-visible investment in the roadmap; it must start as early as the infra allows (i.e., right after M6). M8's quality score and M9's recommender both read what this milestone writes.

**Dependencies.** M6 (Celery for the aggregation job; Alembic for the schema).

**Database changes** (all **Django-owned** — these are user-facing per Principle 2):
- `user_events` — append-only: `user_id, event_type (impression|click|dwell|scroll|save|hide|search|digest_click), content_type, content_id, value (numeric, e.g. dwell ms / scroll %), created_at`. **[Core]**
- `saved_items` — user's saved/bookmarked content + read-state. **[Core]**
- Pipeline-owned derived table `user_affinities` (`user_id, dimension (topic|source|entity), key, weight, updated_at`) — written by the nightly job, read by ranking. **[Core]** *(Owned by the pipeline because the ranking process is its consumer and computes it; Django only reads it. This is the correct side of the boundary.)*
- Widen/stop-truncating the transcript column so **full transcripts are captured** going forward (processing deferred to M12). **[Core]** *(Rationale: same as event logging — capture now, process later. Truncated-at-scrape data is unrecoverable.)*

**Backend changes.**
- Event ingestion endpoints (batched impressions; single-event beacons). Rate-limited, first-party only. **[Core]**
- Digest links become tracked **redirect URLs** so digest CTR is measurable. **[Core]**
- Nightly Celery job: aggregate raw events → `user_affinities` (time-decayed); prune raw events past retention (e.g. 90 days). **[Core]**
- Saves/read-state CRUD. **[Core]**

**Frontend changes.**
- A small **vanilla-JS beacon** (`navigator.sendBeacon` on `visibilitychange` for dwell; `IntersectionObserver` for impressions/scroll depth). No framework. **[Core]**
- Save button + "show less like this" control on cards/detail. **[Core]**
- A **Library** page (saved + read history). **[Core]**

**ML/AI components.** None — this milestone *feeds* ML. It only computes deterministic aggregations.

**Infrastructure requirements.** Celery beat entry for the nightly job. Event volume is modest at current scale but design the table append-only and indexed on `(user_id, created_at)`.

**Complexity.** **M.**

**Portfolio impact.** **Medium** on its own (saves/library are visible and expected); **foundational** for the high-impact milestones. Frame it in the portfolio as "I built the event pipeline that trains the recommender."

**Risks.**
- *Email opens are near-worthless* (Apple Mail Privacy Protection auto-fires open pixels). **Do not track opens as signal; track digest clicks.** [decision — see Parking Lot]
- Privacy/consent: it's all first-party, but publish a short privacy note and keep retention short. Cheap now, painful if retrofitted.
- Bot/self traffic polluting early data — exclude staff/self user IDs from aggregation.

**Success criteria.**
- Clicking, dwelling on, and saving an item produces rows in `user_events`/`saved_items`.
- The nightly job produces sane `user_affinities` for a test user with synthetic-but-realistic events.
- Digest link clicks are attributable to a user + item.
- Full transcripts (not truncated) are present for newly scraped videos.

---

### M8 — Content Intelligence Layer

**Objective.** Give every content item rich, structured, queryable metadata; turn the corpus from "rows of text" into a dataset. Fix duplication. Produce a transparent quality score whose *inputs are logged*.

**Why now.** This is the substrate for both the recommender (M9) and insights (M11): taxonomy, entities, clusters, and quality scores are what those milestones consume. It also delivers immediate visible wins (dedup fixes the repetitive feed today; topic filters improve browsing) so it's not purely enabling.

**Dependencies.** M6 (queue for enrichment/scoring jobs, Alembic). M7 is *not* strictly required but its popularity signals enrich the score once present.

**Database changes** (pipeline-owned):
- `taxonomy_topics` lookup (~25–30 controlled topics) + `content_topics` join. **[Core]** The 15 seeded Django `Interest` rows get an FK to taxonomy topics so user interests and content topics share **one vocabulary** (Principle 5). **[Core]**
- `entities` (company/model/person/technology) + `content_entities` mention join. **[Core]**
- `content_clusters` + cluster membership (same story across sources). **[Core]**
- `content_scores` — quality score **plus a snapshot of the feature vector that produced it** (Principle 7), with a `score_version`. **[Core]**
- New enrichment fields on content: `content_type` (research/product-launch/tutorial/opinion/funding/…), `technical_depth` (1–5), structured summary fields (key points / technical / business angle), `why_it_matters`. **[Core]**

**Backend changes.**
- **Consolidate all enrichment into ONE structured LLM call** per item (Principle 4): summary + topics + content_type + depth + entities + why_it_matters + structured fields, as validated JSON. This *replaces* the current separate summary pass. **[Core]**
- Embedding-based **story clustering** job (agglomerative over pgvector neighbors). **[Core]**
- Quality-score job (heuristic v1) with feature logging. **[Core]**
- **Popularity re-fetch** job: hours after ingest, re-pull native engagement (Reddit upvotes, HF downloads, GitHub stars) — popularity at scrape time is ~0 and misleading. **[Nice-to-have]** (high value, but only for sources that expose it)
- Deliberate, **versioned** corpus backfill of enrichment (run on Ollama local fallback to avoid Groq bulk cost). **[Core]**

**Frontend changes.**
- Topic badges + topic filter on home/feed/search. **[Core]**
- Cross-source **Related** (via cluster membership) replacing today's weak same-source query. **[Core]**
- "Why this matters" on detail pages. **[Nice-to-have]**
- Entity chips on detail pages (link targets built in M11). **[Nice-to-have]**

**ML/AI components.**
- Enum-constrained LLM classification (deterministic vocabulary). **[Core]**
- Embedding clustering (no training; distance-threshold). **[Core]**
- Heuristic quality scorer (weighted feature formula). **[Core]**
- Feature-vector logging → future LightGBM training set (Principle 7). **[Core]**

**Infrastructure requirements.** Enrichment + clustering + scoring as Celery tasks with **rate-limit-aware backoff** (Groq TPM ceilings have bitten this project twice). Ollama for bulk backfill.

**Complexity.** **L.**

**Portfolio impact.** **High.** "Structured content intelligence layer with entity extraction and cross-source story clustering" is a strong, concrete talking point, and the dedup win is immediately demonstrable.

**Risks.**
- LLM taxonomy drift → mitigated by fixed enum vocabulary, not free-form tags.
- Backfill cost → Ollama local + versioned/deliberate backfill, never automatic re-processing.
- Clustering quality (threshold tuning) → evaluate on a hand-checked sample before trusting it for dedup.

**Success criteria.**
- Every newly ingested item has topics, content_type, depth, entities, and a quality score with logged features — from a single LLM call.
- Near-duplicate items across sources are grouped into one cluster; "Related" shows cross-source items.
- User `Interest` rows and content topics resolve against the same vocabulary.

---

### M9 — Owned Recommender + Preferences v2 + Semantic Search

**Objective.** Ship a recommendation engine we own and can explain, demote the LLM to explanation-only in ranking, redesign preferences around real ranker inputs, and add semantic search over the corpus.

**Why now.** This is the portfolio centerpiece and the explicit product goal ("reduce LLM dependency"). It depends on M8's features and M7's affinities. It's also what makes returning users see a feed worth engaging with — which generates more of the data that makes everything else smarter.

**Dependencies.** M8 (features, embeddings, quality score), M7 (affinities, events). M6 (scheduled refresh job).

**Database changes.**
- `user_follows` (entities/topics/sources) — **Django-owned**. **[Core]**
- `user_profile_vectors` — decayed weighted mean of engaged-item embeddings — **pipeline-owned** (the ranking process computes and reads it). **[Core]**
- `ranking_runs` / extend `user_rankings` with `score_version` + per-item feature snapshot for offline eval. **[Core]**
- Preferences v2 fields on the Django profile: difficulty preference, format balance (article↔video), research↔industry lean, reading-time budget. **[Core]**

**Backend changes.**
- **Two-stage ranker** (Principle 6): (1) candidate generation — recency window + exclusions + followed entities + pgvector similarity to the user profile vector (~200 items); (2) scoring — transparent weighted linear combination of interest/topic match, quality score, freshness decay, learned source affinity, novelty penalty; (3) **MMR diversification** so the feed isn't 10 near-identical items. **[Core]**
- Move ranking to its **own scheduled job**, decoupled from digest cadence, so `/feed` stays fresh. **[Core]**
- **Semantic search** endpoint (pgvector similarity over item embeddings). **[Core]**
- Optional "answer from recent AI news, with citations" RAG mode on search. **[Nice-to-have / Research]**
- LLM generates the "why recommended" explanation, or (cheaper) it's **templated from scoring features**. **[Core]**

**Frontend changes.**
- Preferences v2 UI. **[Core]**
- Search page (query box → ranked semantic results). **[Core]**
- "Why recommended" chips on feed items. **[Nice-to-have]**
- Follow/unfollow buttons on entity chips. **[Core]** (targets fully realized in M10/M11)

**ML/AI components.**
- Content-based two-stage recommender (no cross-user data needed — correct at current scale). **[Core]**
- MMR diversification. **[Core]**
- **Offline evaluation harness**: NDCG@10 / MAP against held-out clicks; ranker versioning; shadow-mode comparison. **[Core]** *(This is what lets us later prove a new ranker beats the old one — critical for credibility.)*
- **LightGBM LambdaMART (learning-to-rank) upgrade** — slots into the scoring stage once ~20–50k interaction events exist. Trained on M8's logged features + M7's events. **[Research → Core-when-data-ready]** *(Floating track: promote when data volume justifies; evaluate offline before it takes over.)*

**Infrastructure requirements.** Scheduled ranking-refresh Celery task. pgvector index (IVFFlat/HNSW) tuning as corpus grows.

**Complexity.** **L.**

**Portfolio impact.** **Highest.** A hand-built two-stage recommender with an offline eval harness and a documented "why not collaborative filtering at this scale" decision is a genuinely strong ML-engineering artifact.

**Risks.**
- **Filter bubble** — reserve a 10–15% exploration slice of off-profile items in every feed. **[Core mitigation, not optional]**
- **Cold start** for new users — fall back to onboarding priors + trending (M11); the bones already exist.
- Over-tuning weights by intuition — the eval harness is the guardrail; don't ship weight changes without measuring.

**Success criteria.**
- Two different users with different interests/affinities get demonstrably different, diversified feeds — with zero LLM call in the ranking path.
- Semantic search returns relevant items for a natural-language query.
- The eval harness produces an NDCG number for a ranker version against held-out events.
- Removing the LLM entirely still yields a working, ranked, explained feed.

---

### M10 — User Sources & People Following

**Objective.** Let users extend their own content universe (feeds, channels, orgs) and follow people — the payoff of the Source Registry investment and the top Pro differentiator.

**Why now.** Depends on M8 (AI-relevance gate needs the embedding centroid + entities). High perceived value at modest effort because the registry + generic RSS adapter already exist. Comes after the recommender so added sources immediately benefit from good ranking.

**Dependencies.** M8 (centroid, entities), Source Registry (exists), M6 (scraping as scheduled tasks).

**Database changes.**
- Extend `sources` with `created_by`, `visibility` (global/user), validation metadata — **pipeline-owned** (it's a pipeline table). **[Core]**
- `user_source_subscriptions` join — **Django-owned**. **[Core]**
- `alert_rules` (entity/keyword) — **Django-owned**. **[Nice-to-have → Pro]**
- `person_entities` linking a person to their scrapeable footprint (blog RSS, YouTube, arXiv author, GitHub, Substack) — **pipeline-owned**. **[Core]**

**Backend changes.**
- Add-source flow with **canonicalization** (dedupe by feed URL; fetch once globally even if N users add it — Principle 1). **[Core]**
- **AI-relevance gate**: fetch candidate feed's last ~10 items → embed → mean cosine vs. AI-corpus centroid → accept / reject / gray-zone (keyword-density fallback, accept-but-flag low-trust with a quality haircut). **Re-validate monthly** (feeds drift). **[Core]**
- Per-user source caps + fetch-frequency floors (abuse control; Free vs Pro limits). **[Core]**
- Mention detection surfaces existing corpus items that mention a followed person. **[Core]**
- Alert evaluation job → notification/email. **[Pro]**

**Frontend changes.**
- "Add a source" UI with live relevance feedback. **[Core]**
- Manage subscriptions. **[Core]**
- Follow-a-person UI. **[Core]**
- Alert rule management. **[Pro]**

**ML/AI components.** Embedding-centroid relevance classifier (no training; threshold). **[Core]**

**Infrastructure requirements.** User-added feeds fold into the existing scheduled scraping; monitor their health (feeds into M13 ops).

**Complexity.** **M.**

**Portfolio impact.** **High.** "Users extend the ingestion graph, gated by an embedding-based relevance classifier" demonstrates the registry architecture paying off.

**Risks.**
- Abuse / feed spam → caps, relevance gate, frequency floors.
- **LinkedIn following is explicitly out** (see Parking Lot) — the person-entity aggregation is the sanctioned alternative.
- Scraper sprawl → health monitoring (M13) becomes more urgent as user feeds multiply.

**Success criteria.**
- A user adds a valid AI blog and sees its items; an off-topic feed is rejected with a clear message.
- The same feed added by two users creates one global source, two subscriptions.
- Following a person surfaces both their output and news mentioning them.

---

### M11 — Insights & Trending

**Objective.** Cross the line from *aggregator* to *intelligence platform*: tell users what's happening and why, not just what was published.

**Why now.** Highest product-identity impact, but structurally dependent on M8's entities + clusters and enriched by M7's engagement. Ship it once the substrate is trustworthy.

**Dependencies.** M8 (hard: entities, clusters), M7 (engagement enriches trending), M9 (feed surfaces trending).

**Database changes** (pipeline-owned):
- `trends` / topic-entity mention time-series + baseline stats. **[Core]**
- `entity_timelines` (materialized for entity pages). **[Core]**
- `trend_reports` (generated narratives, with cited source items). **[Pro]**

**Backend changes.**
- **Trending v1 — deliberately LLM-free**: burst detection (z-score of topic/entity mention frequency vs. trailing 30-day baseline) + cluster-size velocity. Pure SQL + scheduled job. **[Core]**
- Entity page assembly (timeline, mention sparkline, related entities). **[Core]**
- Weekly **grounded, cited** trend narrative (LLM over *retrieved* cluster/entity data only, inline citations). **[Pro]**

**Frontend changes.**
- Home "Trending" module. **[Core]**
- Entity pages (`/entity/openai`). **[Core]**
- Story-cluster view (one story, all sources). **[Nice-to-have]**
- Weekly insight report page/email. **[Pro]**

**ML/AI components.**
- Statistical burst detection (no LLM). **[Core]**
- Retrieval-grounded narrative generation. **[Pro / Research]** — highest hallucination risk on the roadmap; ship *last within the milestone*, strictly grounded + cited.

**Infrastructure requirements.** Scheduled trend-computation job; consider a small materialized-view refresh cadence for entity pages.

**Complexity.** **M–L.**

**Portfolio impact.** **Highest** for product identity. "It detects and explains emerging AI trends" is the pitch that separates this from every other feed reader.

**Risks.**
- **Insight hallucination is a trust risk, and trust is the product.** Ground strictly in retrieved data; cite every claim; never let the narrative invent connections. This is why narratives are the last thing built here.
- Burst detection false positives on low-volume topics → minimum-volume floors before a topic can "trend."

**Success criteria.**
- The Trending module reflects a real recent spike without any LLM involvement.
- An entity page shows a correct, dated timeline of that entity's news.
- The weekly narrative cites only real corpus items and makes no unsupported claim (spot-checked).

---

### M12 — Deep Media

**Objective.** Make long-form video a first-class citizen: full hierarchical summaries with chapters, and transcription for videos that lack captions.

**Why now.** Self-contained and demo-friendly, but lower on acquisition/retention value than the intelligence milestones, so it comes after them. Depends on M6 (queue) and M7 (full transcript capture already in place).

**Dependencies.** M6 (queue), M7 (transcripts captured), tier gates (M6 scaffold).

**Database changes** (pipeline-owned):
- Chunk-level summaries with timestamps. **[Core]**
- STT job status/metadata. **[Core]**

**Backend changes.**
- **Chunked map-reduce summarization**: summarize ~10-min chunks → summarize the summaries; store chunk summaries for timestamp deep-links. **[Core]**
- Transcript fallback chain: manual captions → **auto-captions** (covers ~90%+ of gaps) → STT only for the relevance-prefiltered residue. **[Core]**
- Tier gate: deep long-video processing = **Pro**; short videos for everyone. **[Pro]**

**Frontend changes.**
- Chaptered video summaries with timestamp deep-links to YouTube. **[Core]**
- (Video embeds already replaced by thumbnail-link — no iframe reliability dependency here.)

**ML/AI components.**
- Hierarchical summarization (existing LLM, chunked). **[Core]**
- **faster-whisper** (CTranslate2) `distil-large-v3` / `large-v3-turbo` for STT. **[Core]**
- **Public daily "AI Compass Brief" podcast** — one shared generation/day, podcast RSS. **[Nice-to-have]** *(reframed as a marketing channel, not a per-user feature — see M-audio decision in Parking Lot)*

**Infrastructure requirements.** STT is compute-heavy → background queue jobs, gated, run from a machine with a residential IP (YouTube blocks datacenter IPs for audio pulls). yt-dlp audio download sits in ToS gray area — acceptable at portfolio scale, documented.

**Complexity.** **M.**

**Portfolio impact.** **Medium–High** for demos ("summarize a 2-hour podcast into navigable chapters" demos extremely well).

**Risks.**
- LLM rate limits on long transcripts → queue + backoff + Ollama fallback for bulk.
- STT compute/time → gated + prefiltered (don't transcribe low-quality content nobody will be recommended).
- yt-dlp / IP blocking → run from appropriate host; treat as best-effort.

**Success criteria.**
- A 2-hour video yields a chaptered summary with working timestamp links.
- A caption-less video is transcribed via the fallback chain and flows through normal enrichment.

---

### M13 — SaaS Hardening & Monetization

**Objective.** Turn on the business and make the app production-safe for real users.

**Why now.** Last, deliberately (Principle 12). Charging before M8–M11 exist means charging for an aggregator; billing is commodity work with zero learning value and zero revenue at zero users. Everything it gates was designed in from M6.

**Dependencies.** All prior milestones (it monetizes them). Entitlement scaffold from M6.

**Database changes.** Stripe customer/subscription mapping — **Django-owned**. Email-verification/reset token tables (Django built-ins). **[Core]**

**Backend changes.**
- Auth hardening: email verification, password reset, login rate limiting. **[Core]** *(mandatory before any paying user)*
- Stripe integration + webhook → flips `plan`; enforcement already wired since M6. **[Core]**
- Public **REST API** (DRF) — natural Pro feature. **[Pro / Nice-to-have]**
- **Scraper health / ops dashboard** (surface `last_success_at`, dead-feed alerts). **[Core]** *(operational necessity at 20+ sources plus user feeds)*

**Frontend changes.** Pricing page, upgrade flow, account/billing dashboard, usage dashboard. **[Core]**

**ML/AI components.** None.

**Infrastructure requirements.** Stripe (test mode fine for portfolio), transactional email provider for verification/reset, monitoring for the ops dashboard.

**Complexity.** **M** (low novelty, but breadth).

**Portfolio impact.** **Low novelty**, but a working pricing page + enforced entitlements + auth hardening completes the "real SaaS" story. The ops dashboard is a genuine operational-maturity signal.

**Risks.** Mostly correctness/security (auth, webhook idempotency). Low architectural risk because entitlements were threaded through early.

**Success criteria.**
- A user verifies email, upgrades via Stripe (test), and immediately gains Pro entitlements.
- Free-plan limits are enforced everywhere they're supposed to be.
- The ops dashboard flags a deliberately-broken feed.

---

## 5. Free vs Pro — entitlement plan

Gate on **real marginal cost or clear premium value**, never on things that starve our own systems.

| Capability | Free | Pro | Rationale |
|---|---|---|---|
| Interests / topics | **Unlimited** | Unlimited | Interests are training signal for *our* recommender — never cap them (would starve ranking to manufacture upsell). |
| Daily digest | ✅ | ✅ richer | The digest is the retention engine; gate richness, not existence. |
| Custom sources | 3 | Unlimited | Each adds real scraping load. |
| People follows | few | Unlimited | Aggregation cost. |
| Long-video deep summaries | short only | ✅ | Real LLM + STT compute. |
| STT for caption-less video | — | ✅ | Compute-heavy. |
| Real-time alerts | — | ✅ | Premium value, notification cost. |
| Historical trend archive / weekly insight report | limited | ✅ | Stored-history + generation value. |
| Semantic search | ✅ basic | ✅ + RAG answers | RAG has LLM cost. |
| Public API | — | ✅ | Classic Pro gate. |
| Audio / podcast | public daily brief (all) | per-item audio | Shared audio is ~free; per-item scales with use. |

---

## 6. Cross-cutting risk register

**Technical.** No migrations until M6 (top risk — that's why M6 is first). Single-process pipeline vs. background-job demand (M6 fixes). Groq rate limits (already hit twice) → one-enrichment-call consolidation + queued backoff + Ollama fallback. Embedding model lock-in → `model_name` already stored; keep the discipline. Cross-ORM boundary strain as ML tables multiply → every new table's owner is declared in this doc.

**Product.** Filter bubble (mandatory exploration slice, M9). Cold start (onboarding priors + trending). Insight hallucination (ground + cite, M11). **Feature bloat is the #1 solo-dev risk** — the milestone order is designed so the product is coherent and shippable after *any* milestone; stopping at M9 or M11 still leaves a strong product.

**Cost.** LLM spend scales with items × calls/item → consolidation (Principle 4) is the primary lever; caching second; versioned/deliberate backfill third. STT/TTS are the only compute-heavy items — both gated + queued. Raw events + transcripts → capture, aggregate, prune. **Assume Groq's free tier will not survive the M8 backfill** — plan paid tier or Ollama for bulk.

---

## 7. Recommended execution order

**M6 → M7 → M8 → M9 → M10 → M11 → M12 → M13**, with the **LightGBM ranker as a floating upgrade** promoted into M9's scoring stage whenever interaction volume (~20–50k events) arrives.

The reasoning, in one line each:
- **M6/M7 first** because data capture and infra compound with time and unblock everything; delay is permanent data loss.
- **M8 before M9** because the recommender eats M8's features.
- **M9 before M10/M11** because a good feed drives the engagement that improves every later model, and it's the flagship.
- **M11 (insights) is the identity peak** but sits on M8's substrate, so it can't come earlier.
- **M12 (media) is self-contained** and lower priority than intelligence.
- **M13 (billing) last** because monetizing before the intelligence exists is monetizing an aggregator.

Stop-anywhere property: after M9 you have an owned-recommender product; after M11, an intelligence platform; M12–M13 are enhancement + business.

---

## 8. Parking Lot (deliberately postponed — do not re-litigate without reading this)

| Idea | Status | Reason |
|---|---|---|
| **Neural-network ranking** | Postponed indefinitely | No training data; NNs need millions of examples to beat gradient boosting on tabular features. GBDT (LightGBM) is the correct learned ranker at our scale (M9 floating track). Embeddings already provide the only justified deep-learning component. |
| **Collaborative filtering / matrix factorization / two-tower** | Postponed | All need cross-user co-engagement signal. With <100 users it's pure cold-start — dead on arrival. Revisit only at meaningful MAU. Content-based recommender (M9) is the right approach now. |
| **LinkedIn ingestion / following** | Rejected | No public content API; scraping violates aggressively-enforced ToS (hiQ litigation); authed scraping burns accounts. Sanctioned alternative: person-as-entity aggregation over scrapeable footprints (M10). |
| **Twitter/X ingestion** | Rejected | API pricing is prohibitive; scraping is fragile and adversarial. Poor ROI. |
| **Audience tags as stored labels** (Student/Founder/…) | Rejected | Subjective, unmeasurable, redundant. Tag objective attributes (topic, depth, content_type) and compute audience fit via a persona→attribute matrix (M8/M9). |
| **Per-persona pre-generated summaries** | Rejected as designed | ~7× LLM cost for mostly-unread content. Replaced by extract-once structured fields + on-demand template assembly + per-(item,persona) cache (a later enhancement, not a milestone). Digests get persona tone at send time for free. |
| **Per-user generated audio** | Reframed | Cost scales with users × items. Replaced by shared per-item audio segments (free playlist assembly) + one public daily podcast as a marketing channel (M12). |
| **Citation counts as a news quality signal** | Rejected | Temporal mismatch — a news item's citations at publication are zero. At most, author/venue priors for arXiv. |
| **Region / language preferences** | Postponed | No geo-tagged content and an English-only corpus — nothing for the preference to act on (violates Principle 10). Multilingual is a scraper/LLM-cost project first, a preference toggle never-first. |
| **Per-source manual weight sliders** | Rejected | Learn source affinity from behavior (M7) instead of asking users to hand-tune. Keep only the binary exclude that exists today. |
| **Email open tracking** | Rejected as signal | Apple Mail Privacy Protection auto-fires open pixels, making opens meaningless. Track digest *clicks* via redirects (M7). |
| **Separate "model release pages" source** | Rejected | HF + GitHub releases already cover model launches. |
| **Real-time (per-request) LLM ranking** | Rejected permanently | Violates Principle 6 (LLM out of the ranking hot path) and Principle 1 (batch compute, read on serve). |

---

## 9. Decision Log (amendments to this document)

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-14 | Split old-M6 into M6 (Infrastructure) + M7 (Instrumentation); renumbered to M6–M13. | Mixed risky infra with product features in one ~5-week unit; infra must be independently solid before features build on it. |
| 2026-07-14 | LightGBM ranker is a *floating* upgrade into M9, gated on ~20–50k events, not a fixed milestone. | Can't schedule a data-dependent model by calendar; promote when the data exists, evaluate offline first. |
| 2026-07-14 | Full transcript *capture* pulled forward to M7; *processing* stays M12. | Capture-now-process-later (Principle 7); truncated-at-scrape data is unrecoverable. |

---

*End of roadmap. Amend deliberately; keep the Decision Log honest.*
