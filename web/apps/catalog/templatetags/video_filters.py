# M12 — formats a chunk's start_seconds as M:SS / H:MM:SS for chapter
# timestamp labels (news/video_detail.html).
from django import template

register = template.Library()


@register.filter
def mmss(seconds):
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return ""
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
