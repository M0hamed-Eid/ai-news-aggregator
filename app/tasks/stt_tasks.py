# app/tasks/stt_tasks.py
#
# M12 — drives app/services/stt_service.py off the stt_jobs queue populated
# by YoutubeRepository.bulk_create/create (app/database/repositories/
# youtube_repository.py) whenever a video's captions are unavailable.
# Dispatched by run_pipeline.py's run_stt_dispatch_phase, which claims queued
# rows (queued -> running) AFTER its own transaction commits, then fires
# .delay() per job — never from inside the insert transaction itself, to
# avoid racing get_db_session()'s commit-on-exit.
#
# Runs on its own "stt" queue (app/celery_app.py) — compute-heavy (CPU-bound
# faster-whisper inference), must never share a worker with the
# low-latency "interactive" queue or the default 6-hourly pipeline chain.
#
# Channel-curation gate: per docs/ROADMAP.md's design, STT should only run
# for curated Source-Registry channels. This is currently a no-op — every
# YouTube video already comes from a curated channel (M10's user-source
# submission is RSS-only, no user-submitted YouTube channels exist yet) — so
# no actual filter is implemented here; revisit if that changes.

import logging

from app.celery_app import celery_app
from app.database.session import get_db_session
from app.services.stt_service import DEFAULT_WHISPER_MODEL, MAX_STT_DURATION_SECONDS, SttService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.stt_tasks.transcribe_video_task")
def transcribe_video_task(content_id: int) -> dict:
    from app.database.models.youtube_video import YoutubeVideo
    from app.database.repositories.stt_job_repository import SttJobRepository

    with get_db_session() as db:
        video = db.query(YoutubeVideo).filter(YoutubeVideo.id == content_id).first()
        if video is None:
            logger.error("[STT] youtube_video id=%d not found — dropping job", content_id)
            return {"status": "failed", "reason": "video_not_found"}
        video_id = video.video_id

    service = SttService()

    # Cheap metadata-only fetch (no audio download) to enforce the duration
    # ceiling BEFORE committing to a full audio pull + CPU transcription —
    # deliberately no duration FLOOR (a short caption-less video still needs
    # STT so it can flow through normal enrichment, per M12 success criterion 2).
    try:
        probe_duration = service.get_duration_seconds(video_id)
    except Exception as exc:
        logger.error("[STT] Metadata probe failed for video_id=%s: %s", video_id, exc, exc_info=True)
        with get_db_session() as db:
            SttJobRepository(db).upsert_status(
                content_type="youtube_video", content_id=content_id,
                status="failed", error_message=f"metadata probe failed: {exc}"[:2000],
            )
        return {"status": "failed", "reason": "metadata_probe_failed"}

    if probe_duration > MAX_STT_DURATION_SECONDS:
        logger.warning(
            "[STT] video_id=%s duration=%ds exceeds MAX_STT_DURATION_SECONDS=%d — skipping",
            video_id, probe_duration, MAX_STT_DURATION_SECONDS,
        )
        with get_db_session() as db:
            SttJobRepository(db).upsert_status(
                content_type="youtube_video", content_id=content_id, status="skipped_too_long",
            )
        return {"status": "skipped_too_long", "duration_seconds": probe_duration}

    try:
        segments, duration_seconds = service.transcribe_youtube_video(video_id)
    except Exception as exc:
        logger.error("[STT] Transcription failed for video_id=%s: %s", video_id, exc, exc_info=True)
        with get_db_session() as db:
            SttJobRepository(db).upsert_status(
                content_type="youtube_video", content_id=content_id,
                status="failed", error_message=str(exc)[:2000],
            )
        return {"status": "failed", "reason": str(exc)[:200]}

    full_text = " ".join(seg["text"] for seg in segments)

    with get_db_session() as db:
        v = db.query(YoutubeVideo).filter(YoutubeVideo.id == content_id).first()
        if v is not None:
            v.content = full_text
            v.transcript_segments = segments
            v.duration_seconds = duration_seconds
        SttJobRepository(db).upsert_status(
            content_type="youtube_video", content_id=content_id, status="completed",
            transcript_source="stt", whisper_model=service.model_size,
        )

    logger.info(
        "[STT] Completed video_id=%s duration=%ss segments=%d — will flow through normal enrichment next pass",
        video_id, duration_seconds, len(segments),
    )
    return {"status": "completed", "duration_seconds": duration_seconds, "segments": len(segments)}
