# app/utils/reading_time.py
#
# Reading-time estimate for articles, watch-time estimate for videos.
# Note: the video estimate is approximate — we don't store the actual video
# duration (YouTube's RSS feed doesn't include it), so we estimate from
# transcript length at typical speaking pace instead. Good enough for a
# "X min" label; not exact.

def estimate_reading_minutes(word_count: int, words_per_minute: int = 200) -> int:
    return max(1, round(word_count / words_per_minute))


def estimate_watch_minutes(transcript_word_count: int, words_per_minute: int = 150) -> int:
    return max(1, round(transcript_word_count / words_per_minute))