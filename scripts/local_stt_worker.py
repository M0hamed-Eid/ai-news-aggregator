# scripts/local_stt_worker.py
#
# Graduation-week bridge (delete after): runs the SAME transcription this
# project's real STT worker runs (app/services/stt_service.py -- yt-dlp +
# faster-whisper), but from THIS machine's residential IP instead of the
# EC2 box's datacenter IP. YouTube blocks yt-dlp audio downloads from the
# EC2 IP (confirmed live: "Sign in to confirm you're not a bot" / HTTP 403
# on every recent attempt, see stt_jobs.error_message in prod) -- residential
# IPs aren't subject to that block.
#
# Never touches the DB directly: fetches the pending-video list over SSH
# (read-only `docker exec ... psql`), transcribes locally, ships the result
# to the server, and applies it with apply_stt_result.py running INSIDE the
# pipeline container -- so the actual write is byte-for-byte what
# app/tasks/stt_tasks.py would have produced, no separate write path to
# drift out of sync with prod.
#
# Manual, not scheduled -- run again whenever there's a new batch of
# caption-less videos:
#   .venv/Scripts/python.exe scripts/local_stt_worker.py
# Deliberately NOT `uv run` -- pyproject.toml/uv.lock pin yt-dlp==2026.7.4,
# which YouTube now blanket-403s (confirmed live, unrelated to IP
# reputation: the pin itself is stale against YouTube's current player/
# cipher checks). `uv run` re-syncs the venv to that locked pin on every
# invocation, silently downgrading a manually-upgraded yt-dlp right back
# to the broken version. This venv has yt-dlp upgraded out-of-band
# (`uv pip install --upgrade yt-dlp`) specifically so invoking the venv's
# own interpreter directly skips that resync.
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Running this file directly (not `python -c`) puts scripts/ on sys.path[0],
# not the repo root -- `from app.services...` below would 404 without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SSH_HOST = "ubuntu@63.176.108.10"
SSH_KEY = str(Path.home() / ".ssh" / "ai-compass-aws.pem")
POSTGRES_CONTAINER = "ai_news_prod-postgres-1"
PIPELINE_CONTAINER = "ai_news_prod-worker-default-1"
APPLY_SCRIPT = Path(__file__).with_name("apply_stt_result.py")


def ssh(cmd: str) -> str:
    result = subprocess.run(["ssh", "-i", SSH_KEY, SSH_HOST, cmd], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ssh failed: {result.stderr}")
    return result.stdout


def fetch_pending():
    out = ssh(
        f"docker exec {POSTGRES_CONTAINER} psql -U ai_news_user -d ai_news -tAc "
        f'"SELECT id, video_id, title FROM youtube_videos WHERE content IS NULL ORDER BY published_at DESC;"'
    )
    rows = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        content_id, video_id, title = line.split("|", 2)
        rows.append((int(content_id), video_id, title))
    return rows


def transcribe(video_id: str):
    from app.services.stt_service import SttService

    service = SttService()
    segments, duration_seconds = service.transcribe_youtube_video(video_id)
    full_text = " ".join(seg["text"] for seg in segments)
    return full_text, segments, duration_seconds, service.model_size


def push_result(content_id, full_text, segments, duration_seconds, whisper_model):
    payload = {
        "content_id": content_id,
        "full_text": full_text,
        "segments": segments,
        "duration_seconds": duration_seconds,
        "whisper_model": whisper_model,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(payload, f)
        local_path = f.name

    remote_json = f"/tmp/stt_result_{content_id}.json"
    subprocess.run(["scp", "-i", SSH_KEY, local_path, f"{SSH_HOST}:{remote_json}"], check=True)
    Path(local_path).unlink(missing_ok=True)

    ssh(
        f"docker cp {remote_json} {PIPELINE_CONTAINER}:/app/_stt_apply.json && "
        f"docker exec {PIPELINE_CONTAINER} uv run python /app/apply_stt_result.py /app/_stt_apply.json && "
        f"docker exec {PIPELINE_CONTAINER} rm -f /app/_stt_apply.json && "
        f"rm -f {remote_json}"
    )


def main():
    # Ships the apply script into the container once per run -- cheap, and
    # means this bridge needs no git commit / redeploy to pick up changes.
    subprocess.run(
        ["scp", "-i", SSH_KEY, str(APPLY_SCRIPT), f"{SSH_HOST}:/tmp/apply_stt_result.py"], check=True
    )
    ssh(f"docker cp /tmp/apply_stt_result.py {PIPELINE_CONTAINER}:/app/apply_stt_result.py")

    pending = fetch_pending()
    print(f"{len(pending)} video(s) with no transcript.")
    ok, failed = 0, 0
    for content_id, video_id, title in pending:
        print(f"--- id={content_id} video_id={video_id} {title[:70]}")
        try:
            full_text, segments, duration_seconds, whisper_model = transcribe(video_id)
        except Exception as exc:
            print(f"  FAILED (transcribe): {exc}")
            failed += 1
            continue
        try:
            push_result(content_id, full_text, segments, duration_seconds, whisper_model)
        except Exception as exc:
            print(f"  FAILED (push): {exc}")
            failed += 1
            continue
        print(f"  OK duration={duration_seconds}s segments={len(segments)}")
        ok += 1

    print(f"\nDone: {ok} transcribed, {failed} failed, out of {len(pending)}.")


if __name__ == "__main__":
    sys.exit(main())
