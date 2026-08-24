# scripts/apply_stt_result.py
#
# Graduation-week bridge (delete after): applies a transcript produced by
# scripts/local_stt_worker.py (run on a residential IP, since YouTube blocks
# yt-dlp audio downloads from this EC2 box's datacenter IP) to the DB.
# Runs INSIDE the pipeline container via `docker exec` + `docker cp`, using
# the exact same models/repository as app/tasks/stt_tasks.py's own DB-write
# block -- this is not a parallel write path, just that same write,
# triggered from outside Celery.
import json
import sys

from app.database.models.youtube_video import YoutubeVideo
from app.database.repositories.stt_job_repository import SttJobRepository
from app.database.session import get_db_session

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

content_id = data["content_id"]

with get_db_session() as db:
    video = db.query(YoutubeVideo).filter(YoutubeVideo.id == content_id).first()
    if video is None:
        print(f"video id={content_id} not found")
        sys.exit(1)
    video.content = data["full_text"]
    video.transcript_segments = data["segments"]
    video.duration_seconds = data["duration_seconds"]
    SttJobRepository(db).upsert_status(
        content_type="youtube_video", content_id=content_id, status="completed",
        transcript_source="stt", whisper_model=data["whisper_model"],
    )

print(f"applied content_id={content_id} duration={data['duration_seconds']}s segments={len(data['segments'])}")
