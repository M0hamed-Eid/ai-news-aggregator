# app/services/rag_service.py
#
# RAG chat orchestration (M14): retrieve -> access-control filter -> dedup/
# budget -> assemble numbered sources -> generate a grounded, cited answer.
# Module-level functions taking `db`, same service shape as relevance_gate.py/
# recipients.py (not a class — there's no per-request state to hold beyond the
# one call).
#
# Reuses EVERYTHING retrieval-side rather than rebuilding it: the SAME
# all-MiniLM-L6-v2 embed_text() the corpus was indexed with, and
# RagChunkRepository.find_similar()'s pgvector cosine query (Phase A). The
# net-new logic here is scope routing, the access-control filter, source
# diversity/token-budget selection, and wiring AssistantAgent's grounded
# generation on top.
#
# Runs entirely inside the pipeline's "interactive" Celery worker (see
# app/tasks/rag_tasks.py) — that process already has sentence-transformers
# loaded (worker_process_init preload, app/celery_app.py) AND the DB session,
# so unlike Django's search.py this does NOT need a separate embed_query_task
# hop: embedding, retrieval, and generation all happen in one call.
#
# M14 Phase C/D split: retrieve_context() does stages 1-5 (condensation stays
# a separate step before it) with NO LLM generation call — reused by both
# answer_question() (the non-streaming Celery task, Phase B/C) and
# build_retrieval_payload() (the streaming path's retrieval-only Celery task,
# Phase D, see app/tasks/rag_tasks.py::rag_retrieve_task). This is the ONE
# place retrieval logic lives regardless of which transport the answer ends
# up delivered through.

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from groq import RateLimitError as GroqRateLimitError
from openai import RateLimitError as OpenAIRateLimitError

from app.agents.assistant_agent import AssistantAgent, Citation, build_system_prompt
from app.database.models.content_topic import ContentTopic
from app.database.models.django_readmodels import (
    DjangoUserExclusion,
    DjangoUserProfile,
    DjangoUserSourceSubscription,
)
from app.database.models.embedding import Embedding
from app.database.models.rag_chunk import RagChunk
from app.database.models.source import Source
from app.database.models.taxonomy_topic import TaxonomyTopic
from app.database.repositories.article_repository import ArticleRepository
from app.database.repositories.rag_chunk_repository import RagChunkRepository
from app.database.repositories.youtube_repository import YoutubeRepository
from app.embeddings.embedding_service import embed_text
from app.llm.client_factory import get_llm_client_and_model
from app.services.recipients import get_source_categories

logger = logging.getLogger(__name__)

CONDENSE_MAX_TOKENS = 120
CONDENSE_MAX_HISTORY_TURNS = 6  # last N messages (not pairs) sent as condensation context — keeps this cheap
_CONDENSE_PROMPT_TEMPLATE = """Given the conversation history and a follow-up message, rewrite the \
follow-up as a single standalone question that makes full sense without the history — resolve any \
pronoun or implicit reference ("it", "this", "that") to what it actually refers to. Preserve the \
user's intent exactly; do not answer it, just rewrite it. If it's already standalone, return it \
unchanged. Respond with ONLY the rewritten question, nothing else.

Conversation history:
{history_block}

Follow-up message: {question}"""

TOP_K_DEFAULT = 8
FETCH_MULTIPLIER = 6          # over-fetch before access-control filtering + dedup, same idea as search.py's limit*2
MAX_CHUNKS_PER_DOCUMENT = 3   # source diversity cap for kb/topic scope — irrelevant for single-document scope
CONTEXT_TOKEN_BUDGET = 2200   # total retrieved-passage tokens fed to the LLM, leaving headroom for system+question+answer
DOCUMENT_CONTEXT_CHAR_BUDGET = 9000  # deterministic current-page fallback when passage index misses a specific article/video

_NO_RESULTS_MESSAGE = (
    "I couldn't find anything in the knowledge base about that. "
    "Try rephrasing, or ask about a specific article or video you're viewing."
)
_UNAVAILABLE_MESSAGE = "The assistant is temporarily unavailable — please try again in a moment."

_VALID_CONTENT_TYPES = {"article", "youtube_video"}


@dataclass
class RetrievalResult:
    mode: str
    question: str  # the (possibly condensed) question actually retrieved against
    sources_block: str = ""
    handle_to_citation: Dict[str, Citation] = field(default_factory=dict)
    scope_note: str = ""
    has_results: bool = False


def _empty_response(message: str) -> dict:
    return {"answer": message, "citations": [], "grounded": False, "suggestions": []}


def condense_query(question: str, history: Optional[List[dict]]) -> str:
    """
    Rewrites a follow-up ("simplify it", "what about the other one") into a
    standalone question using recent turns, so retrieval embeds something
    actually searchable instead of a bare pronoun. `history`:
    [{"role": "user"|"assistant", "content": "..."}], oldest first.

    Uses client_factory's cheap "simple" tier (an 8B-class rewrite, not a
    synthesis task) and degrades to the raw question on ANY failure — a
    condensation miss should never block the whole chat turn. Skipped
    entirely when there's no history (zero added cost/latency for the
    overwhelmingly common single-turn case).
    """
    if not history:
        return question

    client, model = get_llm_client_and_model("simple")
    history_block = "\n".join(
        f"{turn.get('role', 'user')}: {turn.get('content', '')}"
        for turn in history[-CONDENSE_MAX_HISTORY_TURNS:]
    )
    prompt = _CONDENSE_PROMPT_TEMPLATE.format(history_block=history_block, question=question)
    try:
        response = client.chat.completions.create(
            model=model, temperature=0.0, max_tokens=CONDENSE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        rewritten = (response.choices[0].message.content or "").strip().strip('"')
        return rewritten or question
    except (GroqRateLimitError, OpenAIRateLimitError):
        logger.warning("condense_query: rate limited — falling back to the raw question")
        return question
    except Exception:
        logger.warning("condense_query: failed — falling back to the raw question", exc_info=True)
        return question


def _user_access_context(db, user_id: Optional[int]) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    """
    (excluded_categories, excluded_sources, user_visibility_keys, allowed_user_keys)
    for this user. Mirrors RankingService's _user_visibility_source_keys /
    _subscribed_user_source_keys + recipients.py's kind=="category"/"source"
    exclusion split — an independent implementation (own small queries), same
    established pattern as relevance_gate.py/recipients.py, rather than
    importing RankingService (a digest-ranking class with unrelated state).

    A visibility='user' source the caller isn't subscribed to must NEVER
    surface in an answer — this is the RAG-specific leak search.py's own
    access enforcement was flagged as unverified for; retrieval here always
    applies it directly rather than assuming the corpus is safe.
    """
    user_visibility_keys = {key for (key,) in db.query(Source.key).filter(Source.visibility == "user").all()}

    if user_id is None:
        return set(), set(), user_visibility_keys, set()

    profile_row = db.query(DjangoUserProfile.id).filter(DjangoUserProfile.user_id == user_id).first()
    if profile_row is None:
        return set(), set(), user_visibility_keys, set()
    profile_id = profile_row[0]

    exclusions = (
        db.query(DjangoUserExclusion.kind, DjangoUserExclusion.value)
        .filter(DjangoUserExclusion.profile_id == profile_id)
        .all()
    )
    excluded_categories = {value for kind, value in exclusions if kind == "category"}
    excluded_sources = {value for kind, value in exclusions if kind == "source"}

    source_ids = [
        sid for (sid,) in
        db.query(DjangoUserSourceSubscription.source_id)
        .filter(DjangoUserSourceSubscription.profile_id == profile_id)
        .all()
    ]
    allowed_user_keys = set()
    if source_ids:
        allowed_user_keys = {key for (key,) in db.query(Source.key).filter(Source.id.in_(source_ids)).all()}

    return excluded_categories, excluded_sources, user_visibility_keys, allowed_user_keys


def _topic_content_ids(db, topic_slug: str) -> Set[Tuple[str, int]]:
    rows = (
        db.query(ContentTopic.content_type, ContentTopic.content_id)
        .join(TaxonomyTopic, TaxonomyTopic.id == ContentTopic.taxonomy_topic_id)
        .filter(TaxonomyTopic.slug == topic_slug)
        .all()
    )
    return set(rows)


def _retrieve(db, vector: list, mode: str, content_type, content_id, topic_slug, fetch_k: int):
    repo = RagChunkRepository(db)
    if mode == "document":
        return repo.find_similar(vector, content_type=content_type, content_id=content_id, limit=fetch_k)
    if mode == "topic":
        allowed = _topic_content_ids(db, topic_slug)
        if not allowed:
            return []
        hits = repo.find_similar(vector, limit=fetch_k * 4)
        return [(c, s) for (c, s) in hits if (c.content_type, c.content_id) in allowed][:fetch_k]
    return repo.find_similar(vector, limit=fetch_k)  # mode == "kb"


def _fetch_metadata(db, ids_by_type: Dict[str, Set[int]]) -> dict:
    meta = {}
    article_ids = ids_by_type.get("article")
    if article_ids:
        for a in ArticleRepository(db).get_by_ids(list(article_ids)):
            meta[("article", a.id)] = a
    video_ids = ids_by_type.get("youtube_video")
    if video_ids:
        for v in YoutubeRepository(db).get_by_ids(list(video_ids)):
            meta[("youtube_video", v.id)] = v
    return meta


def _citation_url(chunk: RagChunk, parent) -> str:
    if chunk.content_type == "youtube_video" and chunk.start_seconds is not None:
        video_id = getattr(parent, "video_id", None)
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}&t={int(chunk.start_seconds)}s"
    return getattr(parent, "url", "") or ""


def _assemble_sources(selected: List[Tuple[RagChunk, float, object]]) -> Tuple[str, Dict[str, Citation]]:
    lines = []
    handle_to_citation: Dict[str, Citation] = {}
    for i, (chunk, _sim, parent) in enumerate(selected, start=1):
        handle = f"S{i}"
        title = getattr(parent, "title", None) or "(untitled)"
        anchor = f" @ {int(chunk.start_seconds)}s" if chunk.start_seconds is not None else ""
        lines.append(f"[{handle}] ({title}){anchor}: {chunk.text}")
        handle_to_citation[handle] = Citation(
            marker=handle,
            content_type=chunk.content_type,
            content_id=chunk.content_id,
            chunk_index=chunk.chunk_index,
            title=title,
            url=_citation_url(chunk, parent),
            source=getattr(parent, "source", None),
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            start_seconds=chunk.start_seconds,
            end_seconds=chunk.end_seconds,
        )
    return "\n\n".join(lines), handle_to_citation


def _document_context_source(db, content_type: str, content_id: int, parent) -> Tuple[str, Dict[str, Citation]]:
    """Deterministic current-page context so pronoun questions do not depend on vector recall."""
    title = getattr(parent, "title", None) or "(untitled)"
    source = getattr(parent, "source", None)
    url = getattr(parent, "url", "") or ""
    summary = (getattr(parent, "summary", None) or "").strip()
    content = (getattr(parent, "content", None) or "").strip()
    if len(content) > DOCUMENT_CONTEXT_CHAR_BUDGET:
        content = content[:DOCUMENT_CONTEXT_CHAR_BUDGET].rstrip() + "\n[Content truncated for chat context.]"

    embedding_id = None
    row = (
        db.query(Embedding.id)
        .filter(Embedding.content_type == content_type, Embedding.content_id == content_id)
        .first()
    )
    if row is not None:
        embedding_id = row[0]

    handle_to_citation = {
        "S1": Citation(
            marker="S1",
            content_type=content_type,
            content_id=content_id,
            chunk_index=-1,
            title=title,
            url=url,
            source=source,
            char_start=0 if content else None,
            char_end=len(content) if content else None,
        )
    }
    sources_block = "\n".join([
        f"[S1] Current page context",
        f"Title: {title}",
        f"Summary: {summary or '(none)'}",
        f"Source: {source or '(unknown)'}",
        f"URL: {url or '(none)'}",
        f"Embedding ID: {embedding_id if embedding_id is not None else '(not indexed)'}",
        f"Content: {content or summary or '(no content available)'}",
    ])
    return sources_block, handle_to_citation


def _build_scope_note(db, mode: str, scope: str, content_type, content_id, topic_slug, metadata: dict) -> str:
    if mode == "document":
        parent = metadata.get((content_type, content_id))
        if parent is None:  # anchor item's own chunks got access-filtered out — fetch it directly anyway
            parent = (
                ArticleRepository(db).get_by_id(content_id) if content_type == "article"
                else YoutubeRepository(db).get_by_id(content_id)
            )
        if parent is not None:
            noun = "video" if content_type == "youtube_video" else "article"
            return (
                f"The user is currently viewing this {noun}: \"{parent.title}\". Assume any "
                f"unqualified question (\"this\", \"it\", \"what does this mean\") refers to it.\n"
            )
    if mode == "topic" and topic_slug:
        return f"The user is asking within the \"{topic_slug}\" topic — focus your answer on sources related to it.\n"
    return ""


def _document_retrieval_query(question: str, parent) -> str:
    title = getattr(parent, "title", None) or ""
    summary = getattr(parent, "summary", None) or ""
    return "\n".join([
        "Current page retrieval anchor:",
        f"Title: {title}",
        f"Summary: {summary}",
        f"User question: {question}",
    ]).strip()


def retrieve_context(
    db,
    question: str,
    *,
    user_id: Optional[int] = None,
    scope: str = "kb",
    content_type: Optional[str] = None,
    content_id: Optional[int] = None,
    topic_slug: Optional[str] = None,
    top_k: int = TOP_K_DEFAULT,
) -> RetrievalResult:
    """
    Stages 1-5 ONLY (embed -> scope-routed retrieval -> access-control filter
    -> diversity/token-budget selection -> assemble numbered sources) — no LLM
    generation call. `question` should already be condensed by the caller if
    there's conversation history (see condense_query()); this function just
    embeds and retrieves whatever string it's given.

    Retrieval mode is derived from what's actually provided, not trusted from
    `scope` alone (which only shapes the human-readable scope note): document
    scope needs a real (content_type, content_id); topic scope needs a real
    topic_slug; anything else searches the whole knowledge base.
    """
    if content_type in _VALID_CONTENT_TYPES and content_id is not None:
        mode = "document"
    elif topic_slug:
        mode = "topic"
    else:
        mode = "kb"

    empty = RetrievalResult(mode=mode, question=question)

    document_parent = None
    if mode == "document":
        document_parent = (
            ArticleRepository(db).get_by_id(content_id) if content_type == "article"
            else YoutubeRepository(db).get_by_id(content_id)
        )
        if document_parent is None:
            return empty

    retrieval_query = _document_retrieval_query(question, document_parent) if document_parent is not None else question
    vector = embed_text(retrieval_query)
    hits = _retrieve(db, vector, mode, content_type, content_id, topic_slug, top_k * FETCH_MULTIPLIER)
    if not hits and mode != "document":
        return empty

    ids_by_type: Dict[str, Set[int]] = {}
    for chunk, _sim in hits:
        ids_by_type.setdefault(chunk.content_type, set()).add(chunk.content_id)
    metadata = _fetch_metadata(db, ids_by_type)
    if document_parent is not None:
        metadata[(content_type, content_id)] = document_parent

    excluded_categories, excluded_sources, user_visibility_keys, allowed_user_keys = _user_access_context(db, user_id)
    source_categories = get_source_categories(db)

    allowed_hits = []
    for chunk, sim in hits:
        parent = metadata.get((chunk.content_type, chunk.content_id))
        if parent is None:
            continue  # deleted/orphaned since indexing
        src = getattr(parent, "source", None)
        if src in excluded_sources:
            continue
        if source_categories.get(src) in excluded_categories:
            continue
        if src in user_visibility_keys and src not in allowed_user_keys:
            continue  # private, unsubscribed source — must never leak into an answer
        allowed_hits.append((chunk, sim, parent))

    document_context_allowed = False
    if mode == "document" and document_parent is not None:
        src = getattr(document_parent, "source", None)
        document_context_allowed = not (
            src in excluded_sources
            or source_categories.get(src) in excluded_categories
            or (src in user_visibility_keys and src not in allowed_user_keys)
        )

    if not allowed_hits:
        if document_context_allowed:
            sources_block, handle_to_citation = _document_context_source(db, content_type, content_id, document_parent)
            scope_note = _build_scope_note(db, mode, scope, content_type, content_id, topic_slug, metadata)
            return RetrievalResult(
                mode=mode, question=question, sources_block=sources_block,
                handle_to_citation=handle_to_citation, scope_note=scope_note, has_results=True,
            )
        return empty

    per_doc_cap = None if mode == "document" else MAX_CHUNKS_PER_DOCUMENT
    selected: List[Tuple[RagChunk, float, object]] = []
    per_doc_count: Dict[Tuple[str, int], int] = {}
    token_total = 0
    for chunk, sim, parent in allowed_hits:  # already similarity-ordered by the retrieval query
        key = (chunk.content_type, chunk.content_id)
        if per_doc_cap is not None and per_doc_count.get(key, 0) >= per_doc_cap:
            continue
        chunk_tokens = chunk.token_count or 0
        if selected and token_total + chunk_tokens > CONTEXT_TOKEN_BUDGET:
            break
        selected.append((chunk, sim, parent))
        per_doc_count[key] = per_doc_count.get(key, 0) + 1
        token_total += chunk_tokens
        if len(selected) >= top_k:
            break

    if not selected:
        if document_context_allowed:
            sources_block, handle_to_citation = _document_context_source(db, content_type, content_id, document_parent)
            scope_note = _build_scope_note(db, mode, scope, content_type, content_id, topic_slug, metadata)
            return RetrievalResult(
                mode=mode, question=question, sources_block=sources_block,
                handle_to_citation=handle_to_citation, scope_note=scope_note, has_results=True,
            )
        return empty

    sources_block, handle_to_citation = _assemble_sources(selected)
    if document_context_allowed:
        current_sources_block, current_citation = _document_context_source(db, content_type, content_id, document_parent)
        shifted_citations = {}
        for handle, citation in handle_to_citation.items():
            new_handle = f"S{int(handle[1:]) + 1}"
            citation.marker = new_handle
            shifted_citations[new_handle] = citation
        sources_block = current_sources_block + "\n\n" + "\n\n".join(
            block.replace(f"[S{i}]", f"[S{i + 1}]", 1)
            for i, block in enumerate(sources_block.split("\n\n"), start=1)
        )
        handle_to_citation = {**current_citation, **shifted_citations}
    scope_note = _build_scope_note(db, mode, scope, content_type, content_id, topic_slug, metadata)

    return RetrievalResult(
        mode=mode, question=question, sources_block=sources_block,
        handle_to_citation=handle_to_citation, scope_note=scope_note, has_results=True,
    )


def answer_question(
    db,
    question: str,
    *,
    user_id: Optional[int] = None,
    scope: str = "kb",
    content_type: Optional[str] = None,
    content_id: Optional[int] = None,
    topic_slug: Optional[str] = None,
    style: Optional[str] = None,
    top_k: int = TOP_K_DEFAULT,
    history: Optional[List[dict]] = None,
) -> dict:
    """
    Answers one question end-to-end (condense -> retrieve -> generate),
    grounded in the platform's own knowledge base. Returns a plain,
    JSON-serializable dict: {answer, citations, grounded, suggestions} — the
    exact shape app/tasks/rag_tasks.py hands back through Celery to the
    Django view. `history` (optional): prior turns for multi-turn follow-up
    resolution (see condense_query()) — omitted/empty behaves exactly as a
    fresh, single-turn question.
    """
    question = (question or "").strip()
    if not question:
        return _empty_response("Ask me something about the news, an article, or a video.")

    question = condense_query(question, history)

    ctx = retrieve_context(
        db, question, user_id=user_id, scope=scope, content_type=content_type,
        content_id=content_id, topic_slug=topic_slug, top_k=top_k,
    )
    if not ctx.has_results:
        return _empty_response(_NO_RESULTS_MESSAGE)

    result = AssistantAgent().generate(
        ctx.question, ctx.sources_block, ctx.handle_to_citation, scope_note=ctx.scope_note, style=style,
    )
    if result is None:
        return {"answer": _UNAVAILABLE_MESSAGE, "citations": [], "grounded": False, "suggestions": []}

    return {
        "answer": result.text,
        "citations": [asdict(c) for c in result.citations],
        "grounded": result.grounded,
        "suggestions": result.suggestions,
    }


def build_retrieval_payload(
    db,
    question: str,
    *,
    user_id: Optional[int] = None,
    scope: str = "kb",
    content_type: Optional[str] = None,
    content_id: Optional[int] = None,
    topic_slug: Optional[str] = None,
    style: Optional[str] = None,
    top_k: int = TOP_K_DEFAULT,
    history: Optional[List[dict]] = None,
) -> dict:
    """
    Condense + retrieve ONLY — stops before generation. Used by the streaming
    path's retrieval-only Celery task (app/tasks/rag_tasks.py::
    rag_retrieve_task): returns a fully JSON-serializable payload, including a
    READY system_prompt string, so Django's streaming view can open its own
    Groq stream without importing anything from app/ beyond this one call.
    """
    question = (question or "").strip()
    if not question:
        return {"has_results": False, "question": question}

    question = condense_query(question, history)

    ctx = retrieve_context(
        db, question, user_id=user_id, scope=scope, content_type=content_type,
        content_id=content_id, topic_slug=topic_slug, top_k=top_k,
    )
    if not ctx.has_results:
        return {"has_results": False, "question": ctx.question}

    return {
        "has_results": True,
        "question": ctx.question,
        "system_prompt": build_system_prompt(ctx.sources_block, ctx.scope_note, style),
        "handle_to_citation": {handle: asdict(c) for handle, c in ctx.handle_to_citation.items()},
    }
