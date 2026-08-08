# app/tasks/trend_tasks.py
#
# Weekly grounded trend narrative (M11, Pro) — the only genuinely weekly,
# LLM-driven job in this milestone. Burst detection itself is LLM-free and
# rides the existing 6-hourly pipeline chain instead (see run_pipeline.py's
# run_trend_computation_phase) — this task gets its OWN beat entry because
# neither the "every 6h" nor "nightly" cadences fit a once-a-week job, and
# because generating a citation-grounded narrative is a genuinely different
# kind of work (an LLM call over retrieved data) than pure-SQL burst
# detection.

import logging
from datetime import date, datetime, timedelta, timezone

from app.celery_app import celery_app
from app.database.session import get_db_session
from app.agents.trend_narrative_agent import NARRATIVE_VERSION, TrendNarrativeAgent

logger = logging.getLogger(__name__)

TOP_TRENDS_PER_REPORT = 6
MAX_SOURCES_PER_TREND = 5


def _week_bounds(today: date):
    """The most recently COMPLETED Mon-Sun week as of `today`.

    Trigger-day-agnostic on purpose: this used to assume a Monday-morning
    trigger (report on the week before `today`), which silently became
    WRONG — one extra week stale — when the beat schedule moved to Sunday,
    since a Sunday trigger's "current" week (Mon..today) has itself just
    finished. Computing from the most recent Sunday on/before `today`
    handles a Sunday trigger (that Sunday IS today, week already complete),
    a Monday trigger (yesterday's Sunday, matching the old behavior exactly),
    and any other day-of-week this ever gets rescheduled to again."""
    days_since_sunday = (today.weekday() + 1) % 7  # Mon=1 ... Sat=6, Sun=0
    most_recent_sunday = today - timedelta(days=days_since_sunday)
    week_start = most_recent_sunday - timedelta(days=6)
    return week_start, most_recent_sunday


def _render_email_html(claims: list, week_start: date, week_end: date) -> str:
    items_html = "".join(
        f'<div style="margin-bottom:24px;"><h3 style="margin-bottom:4px;">{c["headline"]}</h3>'
        f'<p style="color:#333;">{c["body"]}</p></div>'
        for c in claims
    )
    return f"""
    <html><body style="font-family: -apple-system, sans-serif; max-width:600px; margin:0 auto; padding:16px;">
      <h2 style="margin-bottom:0;">Your AI Compass Weekly Trend Briefing</h2>
      <p style="color:#666; margin-top:4px;">Week of {week_start.isoformat()} to {week_end.isoformat()}</p>
      {items_html}
      <p style="color:#999; font-size:12px; border-top:1px solid #eee; padding-top:12px;">
        Every claim above is grounded in and cited from real items in this week's corpus —
        this briefing is generated without free-form invention.
      </p>
    </body></html>
    """


def _render_email_text(claims: list, week_start: date, week_end: date) -> str:
    lines = [f"Your AI Compass Weekly Trend Briefing — Week of {week_start.isoformat()} to {week_end.isoformat()}", ""]
    for c in claims:
        lines.append(c["headline"])
        lines.append(c["body"])
        lines.append("")
    return "\n".join(lines)


@celery_app.task(name="app.tasks.trend_tasks.generate_weekly_trend_report_task")
def generate_weekly_trend_report_task() -> dict:
    from app.database.models.article import Article
    from app.database.models.content_entity import ContentEntity
    from app.database.models.content_score import ContentScore
    from app.database.models.content_topic import ContentTopic
    from app.database.models.django_readmodels import DjangoUser
    from app.database.models.entity import Entity
    from app.database.models.taxonomy_topic import TaxonomyTopic
    from app.database.models.trend import Trend
    from app.database.models.youtube_video import YoutubeVideo
    from app.database.repositories.trend_report_repository import TrendReportRepository
    from app.services.email_sender import EmailSender

    today = datetime.now(timezone.utc).date()
    week_start, week_end = _week_bounds(today)
    week_start_dt = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    week_end_dt = datetime.combine(week_end, datetime.max.time(), tzinfo=timezone.utc)

    logger.info("[TrendNarrative] Generating report for week %s to %s", week_start, week_end)

    with get_db_session() as db:
        week_rows = (
            db.query(Trend)
            .filter(Trend.date >= week_start, Trend.date <= week_end, Trend.is_trending.is_(True))
            .all()
        )
        if not week_rows:
            logger.info("[TrendNarrative] Nothing trended this week — skipping report generation")
            return {"generated": False, "reason": "no_trends"}

        best_per_key = {}
        for r in week_rows:
            k = (r.dimension, r.key)
            if k not in best_per_key or r.z_score > best_per_key[k].z_score:
                best_per_key[k] = r
        top_rows = sorted(best_per_key.values(), key=lambda r: -r.z_score)[:TOP_TRENDS_PER_REPORT]

        topic_slugs = [r.key for r in top_rows if r.dimension == "topic"]
        entity_ids = [int(r.key) for r in top_rows if r.dimension == "entity"]
        topics_by_slug = {t.slug: t for t in db.query(TaxonomyTopic).filter(TaxonomyTopic.slug.in_(topic_slugs)).all()}
        entities_by_id = {e.id: e for e in db.query(Entity).filter(Entity.id.in_(entity_ids)).all()}

        trending = []
        for r in top_rows:
            obj = topics_by_slug.get(r.key) if r.dimension == "topic" else entities_by_id.get(int(r.key))
            if obj is not None:
                trending.append({"dimension": r.dimension, "key": r.key, "display_name": obj.name})

        if not trending:
            logger.info("[TrendNarrative] Trending rows referenced no resolvable topic/entity — skipping")
            return {"generated": False, "reason": "unresolvable_trends"}

        # Retrieve up to MAX_SOURCES_PER_TREND real corpus items per trend,
        # published within the week, ranked by quality score (best
        # representatives, not just newest) — deduplicated across trends so
        # the same real item never gets two different handles.
        handle_to_ref = {}
        ref_to_handle = {}
        source_lines = []

        def _get_or_assign_handle(content_type, content_id, title, summary):
            ref = (content_type, content_id)
            if ref in ref_to_handle:
                return ref_to_handle[ref]
            handle = f"S{len(handle_to_ref) + 1}"
            handle_to_ref[handle] = ref
            ref_to_handle[ref] = handle
            source_lines.append(f"[{handle}] {title} — {(summary or '')[:280]}")
            return handle

        for t in trending:
            if t["dimension"] == "topic":
                topic = topics_by_slug[t["key"]]
                item_refs = (
                    db.query(ContentTopic.content_type, ContentTopic.content_id)
                    .filter(ContentTopic.taxonomy_topic_id == topic.id)
                    .all()
                )
            else:
                item_refs = (
                    db.query(ContentEntity.content_type, ContentEntity.content_id)
                    .filter(ContentEntity.entity_id == int(t["key"]))
                    .all()
                )

            article_ids = [cid for ctype, cid in item_refs if ctype == "article"]
            video_ids = [cid for ctype, cid in item_refs if ctype == "youtube_video"]

            candidates = []
            if article_ids:
                candidates += [
                    ("article", a.id, a.title, a.summary)
                    for a in db.query(Article)
                    .filter(Article.id.in_(article_ids), Article.published_at >= week_start_dt, Article.published_at <= week_end_dt)
                    .all()
                ]
            if video_ids:
                candidates += [
                    ("youtube_video", v.id, v.title, v.summary)
                    for v in db.query(YoutubeVideo)
                    .filter(YoutubeVideo.id.in_(video_ids), YoutubeVideo.published_at >= week_start_dt, YoutubeVideo.published_at <= week_end_dt)
                    .all()
                ]
            if not candidates:
                continue

            scores = {}
            cand_article_ids = [cid for ct, cid, *_ in candidates if ct == "article"]
            cand_video_ids = [cid for ct, cid, *_ in candidates if ct == "youtube_video"]
            if cand_article_ids:
                for cid, score in db.query(ContentScore.content_id, ContentScore.score).filter(
                    ContentScore.content_type == "article", ContentScore.content_id.in_(cand_article_ids)
                ).all():
                    scores[("article", cid)] = score
            if cand_video_ids:
                for cid, score in db.query(ContentScore.content_id, ContentScore.score).filter(
                    ContentScore.content_type == "youtube_video", ContentScore.content_id.in_(cand_video_ids)
                ).all():
                    scores[("youtube_video", cid)] = score

            candidates.sort(key=lambda c: scores.get((c[0], c[1]), 0.5), reverse=True)
            for content_type, content_id, title, summary in candidates[:MAX_SOURCES_PER_TREND]:
                _get_or_assign_handle(content_type, content_id, title, summary)

        if not handle_to_ref:
            logger.info("[TrendNarrative] No real corpus items resolved for any trending item — skipping")
            return {"generated": False, "reason": "no_sources"}

        sources_prompt_block = "\n".join(source_lines)

        agent = TrendNarrativeAgent()
        filtered_claims, raw_claims = agent.generate(trending, handle_to_ref, sources_prompt_block)

        if filtered_claims is None:
            logger.error("[TrendNarrative] LLM call/parse failed entirely — not publishing a report this week")
            return {"generated": False, "reason": "llm_failure"}

        report_repo = TrendReportRepository(db)
        report_repo.upsert_for_week(
            week_start_date=week_start, narrative=filtered_claims, raw_narrative=raw_claims,
            narrative_version=NARRATIVE_VERSION, llm_model=agent.model,
        )

        # Broadcast to effective-Pro users. Runs from THIS process (the
        # pipeline), which has no Django import — DjangoUser mirror
        # replicates entitlements.user_can's exact expiry check (see that
        # mirror's own docstring in django_readmodels.py).
        now = datetime.now(timezone.utc)
        pro_users = (
            db.query(DjangoUser)
            .filter(DjangoUser.plan == "pro", DjangoUser.is_active.is_(True))
            .filter((DjangoUser.plan_expires_at.is_(None)) | (DjangoUser.plan_expires_at >= now))
            .all()
        )

        sender = EmailSender()
        emailed = 0
        if sender.is_configured and filtered_claims:
            body_html = _render_email_html(filtered_claims, week_start, week_end)
            body_text = _render_email_text(filtered_claims, week_start, week_end)
            for user in pro_users:
                subject = f"Your AI Compass weekly trend briefing — {week_start.isoformat()}"
                if sender.send(to_address=user.email, subject=subject, body_html=body_html, body_text=body_text):
                    emailed += 1

    logger.info("[TrendNarrative] Done. %d claim(s) published, %d Pro user(s) emailed", len(filtered_claims), emailed)
    return {"generated": True, "claims_published": len(filtered_claims), "emailed": emailed}
