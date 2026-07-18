# app/services/relevance_gate.py
#
# AI-relevance gate for user-submitted sources (M10). Fetches a candidate
# feed's latest ~10 items, embeds them, and compares their mean embedding to
# an "AI-corpus centroid" (a random sample of the EXISTING corpus's own
# embeddings — since every item in this platform's corpus is AI-related by
# construction, its centroid IS what "AI content" looks like in embedding
# space; no separate labeled dataset needed). Accepts, rejects, or falls
# back to a keyword-density check in the gray zone between the two
# thresholds — mirroring how M8 handled EnrichmentAgent's graceful
# degradation and clustering-threshold tuning: pick defensible defaults,
# then validate live against real feeds before trusting them (see
# .wolf/cerebrum.md's M10 Decision Log entry for the actual feeds used and
# the resulting threshold choice).
#
# Deliberately NOT cached/precomputed: the centroid is recomputed fresh each
# call from a random sample of `embeddings` (cheap at this project's current
# corpus size — a few thousand rows). If the corpus grows enough that this
# becomes a real cost, precomputing it periodically is the natural next
# step; not needed yet (no premature optimization).

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

import feedparser
import requests

from app.embeddings.embedding_service import embed_texts

logger = logging.getLogger(__name__)

FEED_FETCH_TIMEOUT_SECONDS = 10
MAX_PREVIEW_ITEMS = 10

CENTROID_SAMPLE_SIZE = 500

# Mean cosine similarity vs. the corpus centroid, over the candidate feed's
# preview items. Above ACCEPT -> accept outright. Below REJECT -> reject
# outright. Between the two -> gray zone, resolved by keyword density.
ACCEPT_THRESHOLD = 0.30
REJECT_THRESHOLD = 0.12

# Gray-zone fallback: fraction of preview items containing at least one
# AI-related keyword. Above this -> accept, but flagged low-trust (a
# quality haircut is applied downstream via ContentScore's own formula
# reading validation_status, not duplicated here).
KEYWORD_ACCEPT_ITEM_FRACTION = 0.5

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning", "neural network",
    "large language model", "language model", "generative ai", "genai", "llm", "gpt",
    "chatgpt", "transformer model", "nlp", "natural language processing",
    "computer vision", "reinforcement learning", "openai", "anthropic", "claude",
    "gemini", "huggingface", "pytorch", "tensorflow", "foundation model",
    "diffusion model", "prompt engineering", "vector database", "embeddings",
    "fine-tuning", "chatbot", "ai model", "ai agent", "ai research",
]
_AI_KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in AI_KEYWORDS) + r")\b", re.IGNORECASE,
)


@dataclass
class RelevanceResult:
    decision: str  # "accepted" | "accepted_low_trust" | "rejected"
    score: float    # mean cosine similarity vs. the centroid (0.0 if never computed, e.g. empty feed)
    message: str    # human-readable, shown directly to the submitting user
    preview_titles: List[str]


def fetch_feed_preview(feed_url: str, max_items: int = MAX_PREVIEW_ITEMS) -> List[str]:
    """
    Fetch the feed's latest `max_items` entries and return "title. summary"
    strings ready to embed. Raises nothing — returns [] on any failure
    (unreachable URL, not a feed, empty feed), so the caller always gets a
    clean reject rather than a 500.
    """
    try:
        response = requests.get(
            feed_url, timeout=FEED_FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "AI-Compass-Source-Validator/1.0"},
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as exc:
        logger.warning("relevance_gate: failed to fetch/parse feed %r — %s", feed_url, exc)
        return []

    if not parsed.entries:
        logger.warning("relevance_gate: feed %r parsed but has zero entries", feed_url)
        return []

    texts = []
    for entry in parsed.entries[:max_items]:
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or "").strip()
        text = f"{title}. {summary}".strip(". ").strip()
        if text:
            texts.append(text)
    return texts


def compute_corpus_centroid(db, sample_size: int = CENTROID_SAMPLE_SIZE) -> Optional[List[float]]:
    """
    Mean (then re-normalized) embedding over a random sample of the existing
    corpus — same normalize-mean-renormalize shape as
    app/tasks/profile_vector_tasks.py's per-user profile vectors, just
    unweighted and sampled from the whole corpus instead of one user's
    engaged items. Returns None if the corpus has no embeddings yet
    (a fresh/empty dev DB) — callers must handle that, not crash on it.
    """
    from sqlalchemy import func as sa_func

    from app.database.models.embedding import Embedding

    rows = (
        db.query(Embedding.embedding)
        .order_by(sa_func.random())
        .limit(sample_size)
        .all()
    )
    if not rows:
        return None

    dim = len(rows[0][0])
    acc = [0.0] * dim
    for (vector,) in rows:
        for i, v in enumerate(vector):
            acc[i] += float(v)
    mean = [x / len(rows) for x in acc]
    norm = sum(x * x for x in mean) ** 0.5
    return [x / norm for x in mean] if norm > 0 else mean


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = sum(float(x) * float(x) for x in a) ** 0.5
    norm_b = sum(float(x) * float(x) for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_density(texts: List[str]) -> float:
    if not texts:
        return 0.0
    matching = sum(1 for t in texts if _AI_KEYWORD_PATTERN.search(t))
    return matching / len(texts)


def evaluate_source(feed_url: str, db) -> RelevanceResult:
    """The full gate: fetch -> embed -> compare to centroid -> decide. The only entry point callers need."""
    preview_texts = fetch_feed_preview(feed_url)
    if not preview_texts:
        return RelevanceResult(
            decision="rejected", score=0.0,
            message="Couldn't read that feed — check the URL points at a working RSS/Atom feed with recent entries.",
            preview_titles=[],
        )

    centroid = compute_corpus_centroid(db)
    if centroid is None:
        # No embeddings exist yet to compare against (a brand-new/empty dev
        # DB) — fail safe to the keyword fallback alone rather than reject
        # everything or silently accept everything.
        density = _keyword_density(preview_texts)
        accepted = density >= KEYWORD_ACCEPT_ITEM_FRACTION
        return RelevanceResult(
            decision="accepted_low_trust" if accepted else "rejected",
            score=0.0,
            message=(
                "Accepted (keyword match only — no corpus embeddings exist yet to compare against)."
                if accepted else
                "Rejected — this doesn't look AI-related, and no corpus embeddings exist yet for a deeper check."
            ),
            preview_titles=[t[:80] for t in preview_texts],
        )

    vectors = embed_texts(preview_texts)
    similarities = [_cosine_similarity(v, centroid) for v in vectors]
    mean_similarity = sum(similarities) / len(similarities)

    if mean_similarity >= ACCEPT_THRESHOLD:
        return RelevanceResult(
            decision="accepted", score=mean_similarity,
            message="This looks like a good fit — added to the registry.",
            preview_titles=[t[:80] for t in preview_texts],
        )

    if mean_similarity <= REJECT_THRESHOLD:
        return RelevanceResult(
            decision="rejected", score=mean_similarity,
            message="This doesn't look AI-related enough for AI Compass — try a more AI-focused feed.",
            preview_titles=[t[:80] for t in preview_texts],
        )

    # Gray zone — keyword density is the tiebreaker.
    density = _keyword_density(preview_texts)
    if density >= KEYWORD_ACCEPT_ITEM_FRACTION:
        return RelevanceResult(
            decision="accepted_low_trust", score=mean_similarity,
            message="Added, but flagged as a borderline fit — it may get a lower quality weighting in rankings.",
            preview_titles=[t[:80] for t in preview_texts],
        )

    return RelevanceResult(
        decision="rejected", score=mean_similarity,
        message="This doesn't look AI-related enough for AI Compass — try a more AI-focused feed.",
        preview_titles=[t[:80] for t in preview_texts],
    )
