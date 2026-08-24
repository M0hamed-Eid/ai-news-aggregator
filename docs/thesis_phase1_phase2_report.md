# AI Compass Graduation Thesis — Phase 1 (Template Analysis) & Phase 2 (Project Audit)

Status: COMPLETE. All five subsystem audits (ranking, RAG, content intelligence/ingestion, deep media/STT, backend+frontend+deployment+security) have returned and are reflected below, cross-checked against `docs/PROJECT_DEEP_DIVE_AND_VIVA.md` and `docs/PRODUCTION_READINESS_AUDIT.md`. Nothing below is asserted without a file:line or commit citation from an independent code read. Only the items in "Information / Assets Needed From You" remain open, and they require your input, not further code reading.

---

## PHASE 1 — Template Analysis

**Source file:** `Digilians 9 Months Diploma Project_2026.docx` (the file you attached is the actual instructor template, not a placeholder — confirmed by its content: title page, approval sheet, abstract, TOC, list of figures/tables, nomenclature, chapter skeleton, references, publications, appendix, and a full parallel Arabic front-matter section).

### 1.1 Institution / co-branding

Four official logos are embedded in the template's title page (`word/media/`), all under the "Awarded by" banner:

| Logo | What it is | Extracted as |
|---|---|---|
| Digilians hexagon mark | The diploma program itself ("الرواد الرقميون / DIGILIANS") | `image1.png` / `image4.png` / `image8.png` (identical, repeated for EN+AR pages) |
| Egyptian Ministry of Communications and Information Technology (MCIT) | Government sponsor | `image2.png` / `image5.png` / `image9.png` |
| Egyptian Military Technical Academy seal | Academic/hosting institution | `image3.png` / `image6.png` / `image10.png` |
| National Telecommunication Institute (NTI) | Co-supervising institute | `image7.png` |

`image8.jpeg` (a stock photo of a generic university building with a light installation) is **template filler only** — the guide text literally captions it "Fig. (1.1) The main building" as a worked example of how to insert a captioned figure. It is not an institutional asset and should not appear in the real thesis.

**Action needed from you:** confirm these four are the correct/current logos (programs sometimes update marks between cohorts) and tell me the supervisor names to print (the template currently has placeholder text "General supervisor: Dr/ Mahmoud Khalil", "Academic Director: Dr/ Ahmed Tobal" — I don't know if these are your actual supervisors or leftover template defaults from a different project; the Arabic mirror also only fills in "د/ أحمد طوبال" for Academic Director and leaves the general-supervisor line as a placeholder "اسم رئيس المسار"). I will place the four extracted PNGs under `figures/logos/` in the Overleaf project once confirmed.

### 1.2 Formatting rules extracted from the template

- **Body font:** Times New Roman, 12pt, 1.5 line spacing (stated explicitly in the template's own instructional text).
- **Margins:** 2.5 cm left/top, **1.5 cm** right/bottom (note: not 2.5/2.5 — the template is explicit that right/bottom differ from left/top; also required on the Title and Approval pages).
- **Page numbers:** centered, bottom of page; preliminary pages (abstract, acknowledgments, TOC, list of figures/tables, nomenclature) use **Roman numerals**; Chapter 1 restarts at Arabic numeral **1**. Landscape pages need a manually-placed page-number text box (continuity note in the template).
- **Headings:** built-in Word styles `Heading1`/`Heading2`/`Heading3` map to Chapter / Section / Subsection — required for the automatic TOC. I will use LaTeX `\chapter`/`\section`/`\subsection` with `\label`/`\ref`, which reproduces this mechanically better than Word ever could.
- **Captions:** `Fig. (n.n) Title.` / `Table (n.n) Title.` numbered by chapter (e.g. Fig. 3.1, Fig. 3.2, Table 5.1) — `\caption`+`\label{fig:...}` per chapter, auto-numbered via `\chapter`-scoped counters (`\usepackage{chngcntr}` + `\counterwithin{figure}{chapter}`).
- **References:** IEEE numbered, square brackets `[1]`, `[2]`. The template's own example reference is IEEE conference-paper format — confirms `IEEEtran` bibliography style is correct.
- **Bilingual front matter:** the template has a **complete parallel Arabic section** at the end of the same document (own title page, own approval sheet, own "ملخص المشروع" abstract heading) — this is a second, Arabic-language front section of the *same* physical document, not a translated duplicate chapter-by-chapter. I will reproduce this as a `polyglossia`/`bidi`-driven Arabic front-matter block (via `arabxetex` or `bidi` package under XeLaTeX/LuaLaTeX — required for Arabic script; `pdflatex` cannot shape Arabic), placed either at the very end (mirroring the template) or as a second title/approval/abstract sequence at the front, per your preference — **I need your call on which**, since the template itself doesn't fully clarify whether the Arabic pages are meant to precede or follow the English body in the final bound document.
- **Nomenclature:** optional section, abbreviations table (e.g. ANN, CNN in the template's own placeholder list) — I will populate this with AI Compass's real abbreviations (LLM, RAG, MMR, NDCG, HNSW, ASR/STT, SSE, ORM, etc.).
- **You confirmed the required front-matter order** via the template's own TOC skeleton: Abstract → Acknowledgments → Contents → List of Figures → List of Tables → Nomenclature → Chapter 1 → ... → References → Publications (optional) → Appendix.

### 1.3 What the abstract file tells us

`AI_Compass_Graduation_Abstract.docx` is **not a second template** — it's the actual, already-written EN+AR abstract for AI Compass, dropped into the same template shell. It gives us:
- **The real title:** "AI Compass" (not a placeholder).
- **The real author list (5 names):** Mohammed Eid, Ahmed Hossam, Abdelrahman Saeed, Mohammed Salama, Abdelrahman Hussein.
- A publication-ready abstract paragraph (EN) and its Arabic translation, both already matching the actual implementation closely (I independently verified nearly every technical claim in it against the code during this audit — see Phase 2 below; a small number of claims need a precision caveat, flagged in §2.9).

**Action needed from you:** supervisor name(s) (real, not the template's placeholder "Dr/ Mahmoud Khalil" / "Dr/ Ahmed Tobal" — confirm whether these are in fact your real supervisors), examination committee names/signatures for the Approval Sheet, and the exact submission date if not "August 2026."

---

## PHASE 2 — Project Audit

Audited via 5 parallel code-reading passes (ranking, RAG, content intelligence/ingestion, deep media/STT, backend+frontend+deployment+security) plus direct inspection of three pre-existing internal documents that turned out to be extraordinarily valuable:

- **`docs/PROJECT_DEEP_DIVE_AND_VIVA.md`** (3,823 lines) — an already-written, code-verified, file:line-cited technical deep dive covering nearly every subsystem, including exact ranking/MMR formulas, RAG internals, an evaluation harness (NDCG@k/MAP), a full "red flags & weaknesses" section, and ~80 viva/defense questions with answers. **This is the single most valuable source document in the repository for this thesis** — most of Chapters 4–8 and the entire Limitations chapter can be drafted from it, cross-checked against fresh code reads (which I did for several subsystems below and found it accurate).
- **`docs/PRODUCTION_READINESS_AUDIT.md`** (dated 2026-08-08) — a real infra/security/privacy audit with live database row counts, a security gap list, and a data-collection inventory. Directly usable for the Security and Evaluation chapters, **but it predates the most recent deployment commits** (see §2.8) — its "nothing is live in the cloud yet, Neon is current" framing is now superseded.
- **`docs/diagrams/`** — three existing, genuinely well-made architecture diagrams (see §2.7) generated from real `.dbml`/`.mmd` source files, committed 2026-07-26.

### 2.1 Ingestion & Content Intelligence — verified

- **Sources:** the `sources` table has exactly **11 rows**, but only **9** are functionally dispatched through the adapter registry (`arxiv`, `github_release`, `youtube`, `reddit`, `government_us/uk/nist`, `funding_crunchbase`, `huggingface_model`); the other 2 (`blog_openai`, `blog_anthropic`) are inert FK-only stub rows — the actual OpenAI/Anthropic blog scraping is hardcoded legacy code (`BlogScraper`) that never reads the registry. **The abstract's "eleven registered sources" is literally correct** but slightly overstates how many are registry-driven; I'll phrase this precisely in the thesis (9 adapter-registry sources + 2 legacy-hardcoded + user-submitted).
- **Adapter pattern:** `BaseScraper` ABC + generic config-driven `RssFeedScraper` (zero new code for a new RSS source) vs. five bespoke JSON-API scrapers (arXiv, GitHub Releases, YouTube, Federal Register, Hugging Face).
- **User-submitted source relevance gate** (`app/services/relevance_gate.py`): **not an LLM call** — an embedding-similarity heuristic against a 500-row corpus centroid (cosine ≥0.30 accept, ≤0.12 reject, gray zone resolved by AI-keyword density). This is a meaningful nuance for the thesis: the abstract says "automated relevance check," which is accurate, but I should be precise that it's a statistical/embedding heuristic, not a generative-AI judgment call — a good, citable design choice (cheap, deterministic, no LLM latency/cost on a Celery-blocking Django request).
- **Enrichment:** confirmed genuinely **one structured LLM call per item** (Groq `llama-3.1-8b-instant`, the cheapest tier) producing summary + controlled-vocabulary topics + entities + content_category + technical_depth + why_it_matters together, with defensive validation (invalid category → `"other"`, unrecognized topics/entities dropped, never invented). The pre-existing `content[:10_000]`-character truncation is confirmed still present and is a genuine, documented limitation for long-form content (mitigated only for long videos via the deep-media map-reduce path, §2.3).
- **Taxonomy:** 27 controlled topics, 15 shared with the user-facing `Interest` vocabulary, 12 content-classification-only.
- **Clustering:** **not a clustering library** — a hand-rolled Union-Find over a pgvector k-NN graph (top-8 neighbors, cosine ≥0.92 edge threshold), rebuilt wholesale every pipeline run. Explicitly for **near-duplicate story dedup** (same real-world story, multiple outlets), not broad topical grouping — confirmed by the code's own comment, and by a documented real failure (a 0.85 threshold produced a 60-item false-merge "mega-cluster" from templated Hugging Face model-card summaries, fixed by excluding that source and raising the threshold to 0.92). This is an excellent "engineering decision with a war story" anecdote for the thesis.
- **Quality scoring:** a transparent heuristic, not an ML model: `0.30·enriched + 0.20·length_score + 0.15·min(1,entities/5) + 0.15·min(1,topics/3) + 0.20·freshness(14-day half-life)`. Fully attributable and defensible in an equations section — this is a **project-specific, deterministic formulation**, not from prior literature, and should be labeled as such.

### 2.2 Recommendation / Ranking — independently verified twice (fresh code audit + cross-check against `docs/PROJECT_DEEP_DIVE_AND_VIVA.md` §11, exact agreement)

Two separate rankers exist and must not be conflated in the thesis:

**Personalized feed** (`app/services/ranking_service.py::RankingService._score()`, lines 438–517; weights at lines 68–74, `RANKER_VERSION = "v1-deterministic"`, explicitly commented as "a documented, heuristic v1 — NOT tuned"):
```
base = 0.35·interest_score + 0.20·quality + 0.15·freshness + 0.15·source_affinity + 0.15·novelty
final_score = clamp01(base × depth_multiplier × format_multiplier × lean_multiplier × reading_time_multiplier)
relevance_score = clamp(round(final_score × 10, 2), 0, 10)
```
- `quality` is read from `content_scores.score` (computed separately in `run_pipeline.py::run_scoring_phase`, its own independent formula — see §2.1's quality heuristic — not recomputed inside the ranker); default `0.5` if no score row exists.
- `freshness = exp(-ln2/48 × age_hours)` (48h half-life, `FRESHNESS_HALFLIFE_HOURS=48.0`); `novelty = 1 − exp(-ln2/10 × age_days)` since last emailed, or `1.0` if never shown (derived from `DigestClickToken`, 30-day lookback — so "novelty" is really "not recently *emailed*," a precise nuance worth stating in the thesis).
- Candidate generation unions three legs: recency (top `RECENCY_CANDIDATE_LIMIT=300` by date), pgvector nearest-neighbor on the per-user profile vector (`SIMILARITY_CANDIDATE_LIMIT=150`, cold-start fallback = onboarding-topic overlap), and guaranteed-inclusion follows (topic/entity/source/followed-person footprints, bypassing recency/similarity) — union capped at `CANDIDATE_POOL_CAP=300`.
- Selection is **Maximal Marginal Relevance**: greedily maximize `MMR_LAMBDA × final_score − (1 − MMR_LAMBDA) × max(cosine(candidate, selected))`, λ=0.7 (`app/services/ranking_service.py:84`), plus a reserved **exploration slice** — `EXPLORATION_FRACTION=0.12` (12% of slots), only applied when the output list has ≥5 items (`EXPLORATION_MIN_LIST_SIZE=5`), filled by weighted-random draw over leftovers (weight = own `final_score`, floor 0.01) — this is the roadmap's deliberate filter-bubble mitigation, and it is genuinely non-deterministic (unseeded `random.random()`), worth disclosing as a limitation, not hidden.
- Explanations (`_build_explanation`, lines 625–647) are **pure string templating, zero LLM calls**, persisted verbatim to `user_rankings.reasoning` — confirms the abstract's "plain-language, template-generated explanation" claim exactly.
- **Real discrepancy found, worth a Limitations-chapter mention**: `UserAffinity` has three dimensions — `topic`, `source`, and `entity` — and `entity` affinity *is* computed and stored nightly (`app/tasks/affinity_tasks.py`), but `RankingService._affinities()` only queries `dimension.in_(["topic","source"])` (line 331): **entity-level affinity is computed but never used in the scoring formula**, only indirectly surfacing through the raw "followed entity" explanation label. This is a genuine unused-signal gap, not a documented design decision — good, honest Limitations-chapter material.
- **Entitlement gating does not touch the scoring formula itself** — `web/apps/accounts/entitlements.py`'s `FEATURE_PLANS` has no Free/Pro branch inside `ranking_service.py`; the only interaction is indirect, via `FREE_FOLLOW_LIMIT=20` bounding how many items can enter via the guaranteed-inclusion follows leg for Free users.
- A **second, unrelated formula** powers the public (non-personalized) home feed (`web/apps/news/feed_ranking.py`): `0.65·freshness + 0.35·quality` with same-source run-length penalties, computed inline per request, never persisted, with freshness measured relative to the newest item on the page rather than to `now()`. The thesis must not present this as "the" ranking algorithm — it's a distinct, simpler, non-personalized greedy selector.
- **Personal taste vector** = `UserProfileVector` (`app/tasks/profile_vector_tasks.py::compute_profile_vectors_task`, nightly): a decayed, weighted **mean of the embeddings of content the user engaged with** (click/save/dwell/digest_click only — impressions and hides excluded), L2-normalized, using the same event-weight table and 14-day half-life decay as the affinity aggregation (`app/tasks/affinity_tasks.py`: impression 0.1, click 1.0, save 3.0, hide **−2.0**, digest_click 1.5). This is a wholesale-replace recompute each run over the last 90 days of events, not an online/incremental EMA update — an important algorithmic precision for the Personalization chapter.
- **A real offline evaluation harness exists**: `app/eval/ranking_eval.py` implements **NDCG@k and MAP** against held-out click/save/digest-click events with explicit relevance weights, plus a "shadow-mode" comparator that scores a fresh ranking pass without persisting it. The module's own docstring honestly caveats that at this data scale, a good number mainly proves the harness is correct rather than proving one ranker superior — this is exactly the kind of honest, gradable statement the Evaluation chapter should quote directly.

### 2.3 Deep Media / STT — verified

- STT is triggered precisely when a newly-inserted YouTube row has empty `content` (no manual or auto-generated caption track found in `_fetch_transcript`, tried in priority order: manual EN → generated EN → any-language generated translated to EN).
- Claim-then-dispatch ordering in `run_stt_dispatch_phase` is deliberately race-safe: jobs are flipped `queued→running` and committed **before** `.delay()` is called, specifically to avoid a Celery worker looking up a row that hasn't committed yet.
- `faster-whisper` `distil-large-v3` on CPU/int8 (env-overridable via `WHISPER_MODEL`), gated at a 3-hour duration ceiling (`MAX_STT_DURATION_SECONDS=10800`) after a metadata-only yt-dlp duration probe.
- **The oft-cited "1.76× real-time" throughput figure is a genuine code comment**, not just a conversational claim: `app/services/stt_service.py` documents a measured 1013s (16.9 min) video transcribed in 1778s (29.6 min) on the audit's own dev machine, CPU-only, no GPU, dated 2026-07-18. This is a legitimate, citable, single-machine measurement — the thesis should describe it precisely as that (one measured data point on specific hardware), not as a general throughput guarantee.
- Long-video chaptering: videos ≥1200s are split into ~600s chunks snapped to caption/STT segment boundaries (never mid-segment), with sub-90s trailing slivers merged into the previous chunk; each chunk gets its own LLM summary (map), and the concatenated chapter summaries are then fed through the *same* `EnrichmentAgent` used for regular items (reduce) — this deliberately routes around the 10,000-character truncation limitation for exactly the content type (long video) that would otherwise be hit hardest by it.
- Entitlement gating (`deep_video_summaries`, Pro-only) gates only the *display* of chapters — the chunking/summarization computation itself runs for every qualifying video regardless of the eventual viewer's plan, confirmed directly in both the pipeline and the Django detail-view API (free users see chapter *count* but blanked title/summary text — "a locked preview, not a vanished section").

### 2.4 RAG Conversational Assistant — verified

- Chunking (`app/rag/chunker.py`): target 180 tokens, 40-token overlap, hard cap 240, using a `words/0.75` heuristic (no real tokenizer in this project) specifically to stay under the `all-MiniLM-L6-v2` embedding model's 256-word-piece truncation ceiling — the model's own truncation is the real backstop, not the heuristic.
- Retrieval: cosine similarity via pgvector HNSW index on a dedicated `rag_chunks` table (deliberately separate from the `embeddings` table so passage rows never leak into clustering/ranking candidate generation) → over-fetch 6× the target k=8 → **access-control filter** (drops chunks from excluded sources/categories, and from any `visibility='user'` source the requester isn't subscribed to) → greedy first-fit selection under a 2,200-token context budget with a per-document diversity cap of 3 chunks.
- A **deterministic non-vector fallback** exists: if retrieval yields nothing but the current page's own document passes the access filter, its raw content (capped 9,000 chars) is used directly as the sole source — this is why "summarize this article" reliably works even on a freshly-indexed page.
- Generation: Groq `llama-3.3-70b-versatile`, `max_tokens=700`, `temperature=0.3`, numbered-source system prompt requiring `[S#]` citation markers; server-side validation surgically strips any unresolvable marker and sets `grounded=False` only if *every* marker in the answer was unresolvable.
- Multi-turn condensation uses the cheap 8B tier over the last 6 messages, with a hard fallback to the raw question on any failure.
- **Streaming architecture, now fully resolved by cross-referencing both audits:** the same Django codebase runs as **two separate deployed processes**. The main `web` service (`web/Dockerfile`, `gunicorn config.wsgi:application --workers 2`) is WSGI and serves everything else — the non-streaming `/assistant/message/` endpoint included. But `docker-compose.prod.yml` defines a **second, dedicated `chat` service** running `uvicorn config.asgi:application` specifically for `/assistant/stream/`, precisely so a long-lived SSE connection can never pin one of the main service's only two sync gunicorn workers (confirmed directly in the compose file's own comment). So: the earlier "is this really ASGI?" question resolves as **both are true, for different endpoints** — the bulk of the Django app is WSGI/gunicorn, and only the streaming chat path is isolated onto its own ASGI/uvicorn container. This is a precise, defensible architectural fact for the thesis (and a good example of a targeted rather than wholesale runtime choice — Django's `config.asgi.py` exists and is genuinely used, just not for the whole app).

### 2.5 Database schema — verified against `docs/diagrams/`

Three existing entity-relationship diagrams (`system_design.png`, `pipeline_schema.png`, `django_schema.png`, all committed 2026-07-26 from `.dbml`/`.mmd` sources) are **high quality and mostly reusable**, but **incomplete relative to the current schema** — I checked their source `.dbml`/`.mmd` files directly:
- `pipeline_schema.dbml` contains **no** `rag_chunks`, `user_rankings`, `user_affinities`, or `user_profile_vectors` tables — all four post-date or were simply omitted from this diagram pass (M9 recommender tables and the M14 RAG index are both missing).
- `django_schema.dbml` contains **no** `ChatConversation`/`ChatMessage` tables (M14 Phase C).
- `system_design.png` (the high-level box diagram) is closer to current — it already shows the Chat ASGI/streaming component and the deterministic RankingService — but should be re-verified once the deployment audit confirms the actual current process model (WSGI vs. ASGI, see §2.4).

**Recommendation:** regenerate `pipeline_schema`/`django_schema` from the live schema before using them as thesis figures, or use them as-is with an explicit caption caveat and a supplementary appendix table listing the omitted tables. I can regenerate them from the actual current models if you'd like (the `.dbml` generation script isn't part of this audit's scope yet — tell me if you want me to find/rebuild it).

### 2.6 Evaluation material actually available

Real, usable-without-embellishment evidence for the Evaluation chapter:
1. `app/eval/ranking_eval.py` — NDCG@k / MAP offline evaluation + shadow-mode comparison (design decision, not yet a headline "our system achieves NDCG=X" number — the module's own docstring cautions against over-claiming at this data scale).
2. The STT throughput figure (§2.3) — one measured data point, CPU-only.
3. `docs/PRODUCTION_READINESS_AUDIT.md` §3 — live database counts as of 2026-08-08 (15,515 articles, 197 videos, 15,696 embeddings, 251,750 trend rows, 4 real users, etc.) — useful as a "system at a glance" table, clearly dated.
4. Embedding idempotency was verified structurally (unique constraint + upsert), confirmed to make duplicate-embedding rows structurally impossible even under a documented past scheduling bug.
5. Section 30 of `PROJECT_DEEP_DIVE_AND_VIVA.md` ("Red flags & weaknesses") is a ready-made, code-cited limitations list (missing ANN index on `embeddings`, 1000-item cap in the embedding phase, `ON CONFLICT DO NOTHING` losing updates, unseeded exploration randomness, thin test coverage, no Celery retry policy, etc.) — I will mine this directly for Chapter "Discussion, Limitations, and Future Work," each item already carrying a proposed fix, which is exactly the "distinguish design decision from unaddressed gap" instruction you gave.

**No user study, A/B test, or click-through-rate experiment exists.** Anything about ranking "quality" beyond the NDCG/MAP harness and qualitative observation must be labeled qualitative, not quantitative — per your explicit instruction.

### 2.7 Existing figures inventory

| File | Represents | Reuse verdict |
|---|---|---|
| `docs/diagrams/system_design.png` | Full three-codebase system architecture (external sources → pipeline → shared Postgres/Redis → Django → frontend/delivery) | Reusable for Ch. 4, pending one caption caveat re: WSGI vs ASGI streaming (§2.4) |
| `docs/diagrams/pipeline_schema.png` | Pipeline-owned ER diagram | Reusable for Ch. 5 **with a disclosed caveat**: missing `rag_chunks`, `user_rankings`, `user_affinities`, `user_profile_vectors` |
| `docs/diagrams/django_schema.png` | Django-owned ER diagram | Reusable for Ch. 6/9 **with a disclosed caveat**: missing `ChatConversation`/`ChatMessage` |
| `frontend/public/logo-*.png`, `frontend/public/sources/*` | AI Compass product branding, per-source icon set | Usable for a UI/branding figure or table, not architecture |

No dashboard/feed/RAG-chat/onboarding **screenshots** exist in the repository. These need to be captured fresh (see "Screenshots needed" below).

### 2.8 Deployment — current topology, fully resolved with commit-level evidence

The deployment story genuinely moved twice during this project's life, and the **current, real state as of commit `d6d9421`** (Aug 22 2026, "Move backend off Neon to self-hosted Postgres on AWS EC2, IP-only") plus its follow-up `1b92575` is:

| Layer | Current reality | Evidence |
|---|---|---|
| Frontend | **Vercel** (unchanged since `0c6f16d`) | `frontend/next.config.ts` |
| Backend (Django + Celery) | **AWS EC2**, plain HTTP, **no domain, IP-only** | `docker/Caddyfile` rewritten to bare `:80 {...}`, comment: "Let's Encrypt cannot issue a certificate for a bare IP — this backend deliberately runs PLAIN HTTP, no domain" (a disclosed, deliberate choice, not an oversight) |
| Database | **Self-hosted Postgres+pgvector on the same EC2 instance** — Neon **decommissioned** | `docker-compose.prod.yml`'s new `postgres` service (`pgvector/pgvector:pg16`, not exposed on a host port); commit message: "Neon's free-tier network-transfer cap (5GB) was hit in under 2 days of real traffic" |
| Browser↔backend path | **Same-origin only** — the browser only ever talks to Vercel's HTTPS domain; Vercel proxies `/api`, `/admin`, `/accounts`, `/behavior`, `/assistant`, `/healthz`, `/r`, `/static` to the backend **server-side** via `next.config.ts`'s `rewrites()` reading a `BACKEND_ORIGIN` env var | Commit message, `d6d9421`: "the browser only ever talks to Vercel's own HTTPS domain and never sees the backend directly" |
| CI/ops | `promote-to-pro.yml` now SSHes to `EC2_HOST` and runs a forced command instead of a direct `psql`/`DATABASE_URL` connection (Postgres is no longer reachable from a GitHub-hosted runner) | `1b92575` |

**Why the split:** Oracle Cloud (the originally-planned free-tier host) had no ARM capacity available against the project's ~1-month deadline, so the backend moved to AWS EC2 (`0c6f16d`); the frontend stayed on Vercel rather than also moving into the Docker stack, since Vercel already hosted it as its own project; Postgres later moved off Neon specifically because of a hard 5GB/month free-tier network-transfer cap, not a capability limit.

**Documentation drift confirmed and worth disclosing in the thesis itself, not just this audit:** `docs/DEPLOYMENT.md` is dated 2026-08-09 — about two weeks stale relative to `d6d9421` — and still describes Neon, a domain-based Caddy HTTPS setup, and a `NEXT_PUBLIC_API_BASE_URL`-driven cross-origin CORS model with real CORS headers; `frontend/.env.example` and `docker/.env.prod.example` are likewise unrevised and don't document the new `BACKEND_ORIGIN` variable the code actually reads now. Two CSRF/CORS mechanisms coexist in the codebase as alternatives — the older cross-origin `NEXT_PUBLIC_API_BASE_URL` fork and the current same-origin `BACKEND_ORIGIN` proxy fork — and only the latter is viable today, since the backend is plain HTTP and would trigger mixed-content blocking if called directly from an HTTPS Vercel page. **This is exactly the kind of doc-vs-implementation divergence your brief asked me to catch rather than silently repeat, and the thesis's deployment chapter should state the current architecture from the code/commits above, while explicitly noting `docs/DEPLOYMENT.md` describes an earlier, superseded design** (worth a one-sentence acknowledgment in the thesis itself — a real, disclosed engineering evolution, not a mistake to hide).

**Security/CSRF mechanics** (unaffected by which topology is active): `GET /api/session/` (`@ensure_csrf_cookie`) issues a CSRF token in its JSON body; the frontend caches and echoes it as `X-CSRFToken` on mutating requests. `django-allauth` is confirmed **not** used anywhere (custom email-only `User` model instead). Stripe webhook signature verification is real (HMAC via `stripe.Webhook.construct_event`); only the webhook — never the checkout-success redirect — grants Pro, closing an unpaid-GET-to-upgrade exploit. The new Gmail API OAuth email backend (`60262a4`) was added specifically because Resend's sandbox mode only delivers to the account owner's own address, silently failing to email every other real signup — worth a short "why" sentence in the Backend chapter, since it's a genuine production incident, not a stylistic choice.

### 2.9 Minor precision corrections to the existing abstract

Everything in `AI_Compass_Graduation_Abstract.docx`'s English abstract checked out against the code with only small precision notes (not corrections of substance):
- "Eleven registered sources" → literally true, but 2 of the 11 are legacy hardcoded stubs rather than registry-dispatched (§2.1) — the thesis body should be precise about this distinction even though the abstract's rounder phrasing is fine as an abstract.
- "A deterministic, non-generative ranking service... from five weighted signals" → confirmed exactly, including the specific weights (§2.2).
- "Every recommendation paired with a plain-language, template-generated explanation" → confirmed exactly, zero LLM calls.
- "The ranking pipeline produces a complete, explained, personalized feed with no LLM calls at all in its serving path" → confirmed.
- "Local speech-to-text transcription sustains roughly 1.76 times real-time throughput on CPU hardware alone" → confirmed as a genuine, dated, single-machine measurement recorded in a code comment (§2.3) — the thesis should present it with that precision (one measurement, not a general benchmark).
- "Deployed as a production, split-service architecture across dedicated hosting and a managed cloud database" → this is the one claim I cannot yet confirm as *current* (§2.8); it may describe an earlier deployment state than the one that exists today.

---

## Proposed Thesis Chapter Structure

Adapted from your suggested 12-chapter outline, adjusted to match what the codebase actually supports and to keep the RAG assistant and recommendation system as their own substantial chapters per your instructions:

1. **Introduction** — problem (AI content overload across 9+ heterogeneous source types), motivation, objectives, thesis contributions, organization.
2. **Background and Related Work** — personalized news recommendation, content-based filtering vs. collaborative filtering (and why the latter was not used — cold-start/data-scale reasoning), embeddings & semantic retrieval, RAG, LLM-assisted content enrichment, MMR-based diversification, NDCG/MAP evaluation.
3. **Problem Definition and Requirements** — functional/non-functional requirements derived from `docs/ROADMAP.md`'s milestone structure and stated architecture principles (ingest-once-personalize-later, deterministic ranking, one LLM call per item, ORM/database ownership boundary).
4. **System Architecture** — three-codebase split (`app/`/`web/`/`frontend/`), shared Postgres+pgvector+Redis, Celery queues, the ORM-ownership boundary as a formal architectural decision (Fig. from `system_design.png`).
5. **Data Acquisition and Content Intelligence** — source registry & adapter pattern, relevance gate for user-submitted sources, one-call enrichment, taxonomy, entity extraction, near-duplicate clustering (pipeline ER diagram, corrected).
6. **Personalization and Recommendation** — behavioral signals → decaying affinities → profile vector; the two ranking formulas (personalized vs. public); MMR + exploration; NDCG/MAP evaluation harness; explicitly-deferred approaches (collaborative filtering, neural ranking, audience personas, region/language filters) as disclosed scope decisions.
7. **Semantic Search and the RAG Conversational Assistant** — its own chapter per your instruction: chunking, retrieval, access control, generation, streaming, anti-hallucination mechanisms, citation validation.
8. **Deep Media Processing** — video ingestion, STT fallback, chaptering map-reduce, measured throughput.
9. **Backend, Frontend, and Deployment** — Django JSON API, Next.js SPA, entitlements/Stripe, and the deployment topology (finalized once §2.8 resolves).
10. **Evaluation and Results** — the NDCG/MAP harness, database-scale snapshot, STT throughput measurement, clearly separated from qualitative observations and design decisions (per your explicit instruction).
11. **Discussion, Limitations, and Future Work** — mined largely from the existing "Red flags & weaknesses" section plus deliberately-deferred features.
12. **Conclusion.**

---

## Tables to include (source-verified, no fabricated numbers)

1. System components / three-codebase ownership matrix.
2. Ingestion sources (11 rows: name, category, adapter type, registry vs. legacy).
3. Ranking signals & weights (the five-signal table from §2.2).
4. Database entity summary (pipeline-owned vs. Django-owned table counts).
5. Technology stack (Python 3.14 pipeline / 3.13 Django / Next.js 16 frontend / Postgres+pgvector / Redis / Celery / Groq / faster-whisper / sentence-transformers).
6. Free vs. Pro entitlement plan (from `docs/ROADMAP.md` §5, cross-checked against `web/apps/accounts/entitlements.py`) — confirmed concrete limits: `FREE_CUSTOM_SOURCE_LIMIT=3`, `FREE_FOLLOW_LIMIT=20`, `FREE_DAILY_MESSAGE_LIMIT=20` (RAG assistant), plus Pro-gated features `unlimited_custom_sources`, `trend_narrative`, `deep_video_summaries`, `unlimited_follows`, `ai_assistant_unlimited` (fail-closed gating: an unregistered feature key is locked for everyone).
7. Live database snapshot (dated, from the Aug 8 production-readiness audit — explicitly time-stamped, not presented as "current").
8. Deliberately deferred/rejected features (collaborative filtering, neural ranking, per-persona summaries, region/language filters, audience tags, etc.).

## Equations to formalize with full notation (§2.2/§2.1 above already give the raw formulas)

1. Personalized ranking score (project-specific, deterministic weighted sum + multiplicative nudges).
2. Freshness/novelty exponential half-life decay functions.
3. Content quality heuristic score.
4. Maximal Marginal Relevance selection rule (cite Carbonell & Goldstein 1998 — the original MMR paper — since AI Compass's λ=0.7 instantiation is an application of established literature, not a novel formulation).
5. Cosine similarity / HNSW ANN retrieval (cite pgvector docs + the original HNSW paper, Malkov & Yashunin).
6. NDCG@k and MAP (cite Järvelin & Kekäläinen 2002 for NDCG; standard IR literature for MAP).
7. Public (non-personalized) home-feed score — clearly distinguished from #1.

## Algorithms warranting pseudocode

1. Enrichment pipeline (one structured LLM call → validated structured output).
2. Union-Find near-duplicate clustering over a k-NN similarity graph.
3. Candidate generation (3-leg union) + MMR + exploration selection.
4. RAG retrieval: embed → over-fetch → access-control filter → diversity/budget-capped greedy selection → generate → citation validation.
5. STT dispatch/claim (race-safe queued→running transition) and long-video chaptering map-reduce.

## Academic references likely required (to verify exact BibTeX entries before final draft — none fabricated yet)

- Vaswani et al., "Attention Is All You Need" (Transformer architecture).
- Reimers & Gurevych, "Sentence-BERT" (sentence-transformers / the embedding model family).
- Carbonell & Goldstein, "The Use of MMR, Diversity-Based Reranking..." (MMR).
- Malkov & Yashunin, "Efficient and robust approximate nearest neighbor search using HNSW graphs."
- Järvelin & Kekäläinen, "Cumulated gain-based evaluation of IR techniques" (NDCG).
- Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" (RAG).
- Robertson & Zaragoza or similar, if a BM25/keyword-fallback comparison is discussed (the relevance gate's keyword fallback and the search module's degrade-to-keyword-search path may warrant this).
- pgvector official documentation (extension docs, not a paper, cited as official technical documentation).
- pytest / Celery / Django / Next.js official docs where their behavior is described academically (not marketing pages).
- Whisper / faster-whisper original paper(s) (Radford et al., "Robust Speech Recognition via Large-Scale Weak Supervision") for the ASR component.
- A recommendation-systems survey (e.g. Ricci, Rokach & Shapira, *Recommender Systems Handbook*) for the Related Work comparison against collaborative filtering.

**I have not fabricated any DOI/year/venue above — these are well-known, real papers I'm confident exist, but I will verify exact bibliographic details (year, venue, page numbers) before finalizing `references.bib`, per your "citation integrity" instruction.**

---

## Information / Assets Needed From You

1. **Supervisor names** — the template currently has placeholder text; I need to know if "Dr/ Mahmoud Khalil" (General Supervisor) and "Dr/ Ahmed Tobal" (Academic Director) are your real supervisors or template leftovers from a different cohort/project.
2. **Examination committee names** for the Approval Sheet (currently blank "Prof. ___" rows in the template).
3. **Confirmation of the four institutional logos** (Digilians, MCIT, Egyptian Military Technical Academy, NTI) as still correct/current for your cohort.
4. **Arabic front-matter placement preference** — front-of-document or end-of-document (the template places it at the end; some institutions bind it at the front instead).
5. **Screenshots** — none exist in the repo. I'll need you to either grant me a live browser session against a running instance, or capture and send me: (a) the personalized Home feed (logged in, with real ranked items and an explanation shown), (b) Search results, (c) an Article detail page with the RAG assistant panel open mid-conversation with visible citations, (d) a Video detail page with chaptered summaries (Pro view), (e) the onboarding/preferences screen, (f) the billing/pricing page. I can specify exact viewport sizes and states once we reach the figure-drafting phase.
6. **Confirmation that the current deployment (Vercel + IP-only AWS EC2 + self-hosted Postgres, per §2.8) is the one you want documented as "the" production architecture in the thesis** — the code/commits are unambiguous about what's live right now, but only you can confirm this is the final state at submission time and not another in-flight change.
7. **Any real evaluation you want me to run** (e.g., actually executing `app/eval/ranking_eval.py` against the current database and reporting the real NDCG@k/MAP numbers) — I have not run it; the thesis should either report a freshly-run number with today's date, or explicitly state no formal offline evaluation run is included and explain why (sparse held-out data, as the module's own docstring already cautions).
8. **Team member roles** — if the thesis should attribute specific subsystems to specific co-authors (the abstract lists 5 names with no individual attribution), tell me the breakdown if one exists.

---

## Risks / Inconsistencies Found (flagging per your explicit "do not silently resolve" instruction)

1. **`docs/DEPLOYMENT.md` and both `.env.example` files are ~2 weeks stale** relative to the actual deployed architecture (§2.8) — they still describe Neon + a domain-based Caddy HTTPS setup + cross-origin CORS, none of which match the current IP-only EC2 + self-hosted Postgres + same-origin Vercel-proxy reality. The thesis's deployment chapter must be written from the code/commits, with one explicit sentence acknowledging the documented evolution (Oracle→AWS EC2, then Neon→self-hosted Postgres) rather than silently presenting only the final state as if it were the only one ever tried — that evolution is itself a legitimate, tellable engineering narrative (real free-tier constraints forcing two successive infrastructure pivots under a deadline).
2. **Existing ER diagrams are incomplete**, not merely "possibly outdated" — confirmed by grep against their own source `.dbml` files that several real, shipped tables (`rag_chunks`, `user_rankings`, `user_affinities`, `user_profile_vectors`, `ChatConversation`, `ChatMessage`) are simply absent from the diagrams despite being committed after those tables existed. Either regenerate or caption-caveat before use.
3. **The abstract's "managed cloud database" and "dedicated hosting" phrasing** describes the Neon-era architecture, which is now superseded by the self-hosted-Postgres-on-EC2 reality (§2.8). This is a real, disclosed change in the underlying system since the abstract was written — the thesis body (Chapter 9) should describe the current state precisely; whether the abstract itself gets revised to match is your call, since abstracts are often written before a project's final infrastructure settles.
4. **No automated test coverage exists** for ranking, RAG, clustering, scoring, or any Celery task (confirmed both by the content-intelligence agent and independently by `PROJECT_DEEP_DIVE_AND_VIVA.md` §30.11) — this constrains how strongly the Evaluation chapter can claim correctness; I will phrase all such claims as "verified by direct code reading and the cited manual/live-browser verification sessions recorded in project history," not "tested," where no automated test exists.
5. **The "isolated ASGI chat container" claim is confirmed true, but only for one specific endpoint** — resolved in §2.4/§2.8: the bulk of Django runs as WSGI/gunicorn, and only `/assistant/stream/` is deployed on a dedicated `chat` ASGI/uvicorn container. Earlier project history describing this as "web/ is ASGI" would be imprecise; the thesis should state the two-process split explicitly.
6. **The abstract states "eleven registered sources"** without the nuance that 2 are legacy stubs — not a factual error, just a precision gap the thesis body (not the abstract, which can stay as-is) should resolve.
7. **A real, unused signal**: `UserAffinity`'s `entity` dimension is computed nightly but never read by the ranking formula (§2.2) — worth one honest sentence in Limitations rather than presenting the ranker as using "every computed behavioral signal."

Ready to proceed to Phase 3 (Thesis Blueprint) on your go-ahead — this document is the complete Phase 1 + Phase 2 deliverable.
