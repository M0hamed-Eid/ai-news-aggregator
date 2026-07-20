# app/rag/chunker.py
#
# Splits a document into passage-sized chunks for RAG retrieval.
#
# Why these sizes?
# ----------------
# The embedding model (all-MiniLM-L6-v2, app/embeddings/embedding_service.py)
# truncates its input at 256 word-piece tokens — anything past that is silently
# dropped before the vector is produced. So a passage MUST stay comfortably
# under 256 tokens or its tail never gets embedded. We target ~180 tokens with
# ~40 tokens of overlap so a fact spanning a chunk boundary still lands whole in
# at least one passage.
#
# There is no tiktoken in this project (see cerebrum), so token counts are
# estimated from a words/token ratio — good enough for budgeting, and the model
# does the real truncation as a backstop.
#
# Two entry points:
#   chunk_article(content)      -> passages with character offsets (citations)
#   chunk_transcript(segments)  -> passages with start/end seconds (deep-links)

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Tuning. Kept module-level so RAG_INDEX_VERSION can be bumped alongside a change.
TARGET_TOKENS = 180
OVERLAP_TOKENS = 40
MAX_TOKENS = 240          # a single unit larger than this is hard-split by words
MAX_CHUNKS_PER_ITEM = 240  # safety cap for pathologically long transcripts
_WORDS_PER_TOKEN = 0.75    # rough English ratio (≈1.33 tokens/word)

# A "sentence" for chunking purposes: a run of non-terminator text ending at
# ., !, ? (followed by whitespace/end) or a blank-line paragraph break. Fuzzy on
# purpose — offsets come from the match span so they always map back to the
# original string even when the split isn't linguistically perfect.
_SENT_RE = re.compile(r"\S.*?(?:[.!?]+(?=\s|$)|\n{2,}|$)", re.DOTALL)
_WORD_RE = re.compile(r"\S+")


@dataclass
class Passage:
    text: str
    token_count: int
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None


def estimate_tokens(text: str) -> int:
    words = len(text.split())
    return max(1, round(words / _WORDS_PER_TOKEN))


# A "unit" is the atom we pack into passages: (text, char_start, char_end, tokens)
_Unit = Tuple[str, int, int, int]


def _split_long(sentence: str, base: int) -> List[_Unit]:
    """Hard-split an over-long sentence into word-windows, preserving offsets."""
    out: List[_Unit] = []
    buf: List[str] = []
    start_off: Optional[int] = None
    last_end = base
    words_per_chunk = max(1, int(TARGET_TOKENS * _WORDS_PER_TOKEN))
    for m in _WORD_RE.finditer(sentence):
        if start_off is None:
            start_off = base + m.start()
        buf.append(m.group())
        last_end = base + m.end()
        if len(buf) >= words_per_chunk:
            t = " ".join(buf)
            out.append((t, start_off, last_end, estimate_tokens(t)))
            buf, start_off = [], None
    if buf:
        t = " ".join(buf)
        out.append((t, start_off if start_off is not None else base, last_end, estimate_tokens(t)))
    return out


def _sentences_to_units(text: str) -> List[_Unit]:
    units: List[_Unit] = []
    for m in _SENT_RE.finditer(text):
        raw = m.group()
        s = raw.strip()
        if not s:
            continue
        t = estimate_tokens(s)
        if t <= MAX_TOKENS:
            units.append((s, m.start(), m.end(), t))
        else:
            units.extend(_split_long(s, m.start()))
    return units


def _pack(units: List[_Unit], make_passage) -> List[Passage]:
    """Greedy-pack units up to TARGET_TOKENS with OVERLAP_TOKENS carry-back."""
    passages: List[Passage] = []
    i, n = 0, len(units)
    while i < n and len(passages) < MAX_CHUNKS_PER_ITEM:
        cur: List[_Unit] = []
        tok = 0
        j = i
        while j < n and (not cur or tok + units[j][3] <= TARGET_TOKENS):
            cur.append(units[j])
            tok += units[j][3]
            j += 1
        passages.append(make_passage(cur, tok))
        if j >= n:
            break
        # Step back so the next chunk re-includes ~OVERLAP_TOKENS of tail context.
        back, k = 0, j - 1
        while k > i and back < OVERLAP_TOKENS:
            back += units[k][3]
            k -= 1
        i = max(k + 1, i + 1)  # always make forward progress
    return passages


def chunk_article(content: str) -> List[Passage]:
    """Chunk article body text into passages carrying character offsets."""
    text = (content or "").strip()
    if not text:
        return []
    units = _sentences_to_units(text)
    if not units:
        return []

    def make(cur: List[_Unit], tok: int) -> Passage:
        return Passage(
            text=" ".join(u[0] for u in cur),
            token_count=tok,
            char_start=cur[0][1],
            char_end=cur[-1][2],
        )

    return _pack(units, make)


def chunk_transcript(segments: Sequence[Dict[str, Any]]) -> List[Passage]:
    """
    Chunk a transcript ([{start, duration, text}, ...]) into time-anchored
    passages. start_seconds/end_seconds bound each passage so a citation can
    deep-link to ?t=<start>.
    """
    segs = [s for s in (segments or []) if isinstance(s, dict) and (s.get("text") or "").strip()]
    if not segs:
        return []

    passages: List[Passage] = []
    i, n = 0, len(segs)
    while i < n and len(passages) < MAX_CHUNKS_PER_ITEM:
        cur: List[Dict[str, Any]] = []
        tok = 0
        j = i
        while j < n and (not cur or tok + estimate_tokens(segs[j]["text"]) <= TARGET_TOKENS):
            cur.append(segs[j])
            tok += estimate_tokens(segs[j]["text"])
            j += 1
        first, last = cur[0], cur[-1]
        start = float(first.get("start", 0.0) or 0.0)
        end = float(last.get("start", 0.0) or 0.0) + float(last.get("duration", 0.0) or 0.0)
        passages.append(Passage(
            text=" ".join((s["text"] or "").strip() for s in cur),
            token_count=tok,
            start_seconds=start,
            end_seconds=end,
        ))
        if j >= n:
            break
        back, k = 0, j - 1
        while k > i and back < OVERLAP_TOKENS:
            back += estimate_tokens(segs[k]["text"])
            k -= 1
        i = max(k + 1, i + 1)
    return passages
