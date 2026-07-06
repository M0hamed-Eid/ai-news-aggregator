# app/utils/youtube.py

def youtube_thumbnail_url(video_id: str) -> str:
    """Same idea as YoutubeVideo.thumbnail_url on the Django side, reused here."""
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"