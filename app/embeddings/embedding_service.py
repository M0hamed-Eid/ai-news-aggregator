# app/embeddings/embedding_service.py
#
# Turns a piece of text into a list of 384 numbers (a "vector") that captures
# its meaning. Two texts about similar topics end up with vectors that are
# close together — that's what makes duplicate detection and search possible.
#
# Runs 100% locally (downloads the model once, ~90MB), no API key, no cost.

import logging
from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """
    Load the model once per process and cache it.
    Without this, every call to embed_text() would reload ~90MB of
    weights from disk — slow and wasteful.
    """
    logger.info(f"Loading embedding model: {MODEL_NAME}")
    return SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> List[float]:
    """Embed a single piece of text. Returns a list of 384 floats."""
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")

    model = _get_model()
    # normalize_embeddings=True: makes cosine similarity math clean and
    # consistent, regardless of which pgvector operator we compare with later.
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Batch version — encoding many texts in one call is much faster than a loop."""
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vectors]