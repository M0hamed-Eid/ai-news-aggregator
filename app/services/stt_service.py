# app/services/stt_service.py
#
# M12 — speech-to-text fallback for videos whose captions are disabled or
# unavailable (app/scrapers/youtube_scraper.py stub-inserts these instead of
# dropping them; app/tasks/stt_tasks.py drives this service off the resulting
# stt_jobs queue). yt-dlp pulls audio-only, faster-whisper transcribes it
# locally (CPU) — no external API, no per-call cost, but compute-heavy and
# meant to run on a dedicated "stt" queue/worker (see app/celery_app.py),
# ideally on a residential-IP host per docs/ROADMAP.md's own infra note.
#
# Output shape is deliberately IDENTICAL to the caption path's segments
# ({"start", "duration", "text"} — see youtube_scraper.py::_fetch_transcript)
# so chunking/duration-derivation code never needs to know which path
# produced a video's transcript.

import logging
import os
import shutil
import tempfile

logger = logging.getLogger(__name__)

DEFAULT_WHISPER_MODEL = os.getenv("WHISPER_MODEL", "distil-large-v3")

# 3-hour ceiling — protects the CPU-bound stt worker from a pathological
# item. Deliberately NO floor: a short caption-less video still needs STT so
# it can flow through normal enrichment (M12 success criterion 2).
#
# Go/no-go throughput finding (measured 2026-07-18, this dev machine, CPU/
# int8, no GPU): distil-large-v3 transcribed a real 1013s (16.9min) video in
# 1778s (29.6min) — a 1.76x REAL-TIME FACTOR (slower than the video itself).
# At the 3h ceiling above, a worst-case video would take ~5.3h to transcribe.
# Accepted as-is rather than downgrading to a smaller/less-accurate model,
# because STT is already architected to be fully async and non-blocking:
# it runs on its own "stt" queue/worker, dispatched from a periodic pipeline
# phase (run_pipeline.py::run_stt_dispatch_phase) that never waits on it, and
# a video's content lands on a LATER pipeline pass once transcription
# finishes. "STT can lag behind ingestion" is expected behavior here, not a
# bug — matches the roadmap's own "portfolio scale" framing for this
# milestone's infra tradeoffs. Revisit WHISPER_MODEL (env override) if this
# ever needs to run at real production video volume.
MAX_STT_DURATION_SECONDS = 10800


class SttService:

    def __init__(self, model_size: str | None = None):
        self.model_size = model_size or DEFAULT_WHISPER_MODEL
        self._model = None  # lazy — a worker with an empty stt queue never needs to load it

    def get_duration_seconds(self, video_id: str) -> int:
        """
        Cheap yt-dlp metadata-only fetch (skip_download) — used to enforce
        MAX_STT_DURATION_SECONDS before committing to a full audio pull.
        """
        import yt_dlp

        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return int(info.get("duration") or 0)

    def transcribe_youtube_video(self, video_id: str) -> tuple[list[dict], int]:
        """
        Returns (segments, duration_seconds). Raises on download or
        transcription failure — app/tasks/stt_tasks.py catches this and
        records it on the stt_jobs row rather than silently swallowing it.
        """
        audio_path = self._download_audio(video_id)
        try:
            return self._run_whisper(audio_path)
        finally:
            # Removes the whole mkdtemp() dir (not just the .wav) — yt-dlp's
            # postprocessing can leave other intermediate files alongside it.
            shutil.rmtree(os.path.dirname(audio_path), ignore_errors=True)

    def _download_audio(self, video_id: str) -> str:
        import yt_dlp

        tmp_dir = tempfile.mkdtemp(prefix="stt_audio_")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmp_dir, f"{video_id}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }],
        }
        url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        expected_path = os.path.join(tmp_dir, f"{video_id}.wav")
        if not os.path.exists(expected_path):
            raise RuntimeError(f"yt-dlp did not produce the expected audio file: {expected_path}")
        return expected_path

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            logger.info(f"Loading faster-whisper model '{self.model_size}' (CPU, int8)")
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def _run_whisper(self, audio_path: str) -> tuple[list[dict], int]:
        model = self._get_model()
        segments_iter, info = model.transcribe(audio_path, vad_filter=True)

        segments = [
            {"start": seg.start, "duration": round(seg.end - seg.start, 3), "text": seg.text.strip()}
            for seg in segments_iter
        ]

        duration_seconds = (
            round(info.duration) if info.duration
            else (round(segments[-1]["start"] + segments[-1]["duration"]) if segments else 0)
        )
        return segments, duration_seconds
