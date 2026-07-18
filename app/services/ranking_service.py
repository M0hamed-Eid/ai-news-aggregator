# app/services/ranking_service.py
#
# Deterministic two-stage recommender (M9) — replaces CuratorAgent's
# LLM-based ranking pass entirely, per Architecture Principle 6 ("we do not
# put an LLM in the hot path of ranking"; the LLM's role shrinks to
# explanations, and even those are now templated, not generated). Runs on
# its own schedule (app/tasks/ranking_tasks.py::rank_all_users_task),
# decoupled from digest send cadence so /feed stays fresh between sends.
#
# Stage 1 — candidate generation: recency window + exclusions + followed
# entities/topics/sources (guaranteed inclusion) + pgvector similarity to
# the user's profile vector (cold-start fallback: onboarding-interest
# topic overlap, per the roadmap's own risk note).
# Stage 2 — scoring: a transparent weighted linear combination (interest/
# topic affinity, quality score, freshness decay, source affinity, novelty
# penalty) times Preferences v2 multiplicative nudges (depth/format/lean/
# reading-time — never hard filters), then MMR diversification + a
# reserved exploration slice of off-profile items (filter-bubble
# mitigation, Core per the roadmap's risk register).
#
# Every scored item's exact feature snapshot is persisted (user_rankings.
# features, Principle 7) — the eval harness (app/eval/ranking_eval.py)
# and any future learned ranker train on this, not just the final score.
#
# Weights/thresholds below are a documented, heuristic v1 — NOT tuned.
# The offline eval harness is the guardrail for ever changing them; see
# Architecture risk register ("over-tuning weights by intuition").

import logging
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import tuple_

from app.database.models.article import Article
from app.database.models.content_entity import ContentEntity
from app.database.models.content_enrichment import ContentEnrichment
from app.database.models.content_score import ContentScore
from app.database.models.content_topic import ContentTopic
from app.database.models.embedding import Embedding
from app.database.models.source import Source
from app.database.models.taxonomy_topic import TaxonomyTopic
from app.database.models.user_affinity import UserAffinity
from app.database.models.youtube_video import YoutubeVideo
from app.database.repositories.digest_click_token_repository import DigestClickTokenRepository
from app.database.repositories.embedding_repository import EmbeddingRepository
from app.database.repositories.user_profile_vector_repository import UserProfileVectorRepository
from app.ranking.types import DigestItem, RankedArticle
from app.services.recipients import Recipient
from app.utils.reading_time import estimate_reading_minutes, estimate_watch_minutes

logger = logging.getLogger(__name__)

RANKER_VERSION = "v1-deterministic"

RECENCY_CANDIDATE_LIMIT = 300
SIMILARITY_CANDIDATE_LIMIT = 150
CANDIDATE_POOL_CAP = 300

FRESHNESS_HALFLIFE_HOURS = 48.0
NOVELTY_HALFLIFE_DAYS = 10.0
NOVELTY_LOOKBACK_DAYS = 30

WEIGHTS = {
    "interest": 0.35,
    "quality": 0.20,
    "freshness": 0.15,
    "source_affinity": 0.15,
    "novelty": 0.15,
}

EXPERTISE_DEPTH_BANDS = {
    "beginner": (1, 2),
    "intermediate": (2, 4),
    "advanced": (3, 5),
}
RESEARCH_CATEGORIES = {"research"}
INDUSTRY_CATEGORIES = {"product-launch", "funding", "announcement", "tooling"}

MMR_LAMBDA = 0.7
EXPLORATION_FRACTION = 0.12
EXPLORATION_MIN_LIST_SIZE = 5


@dataclass(eq=False)  # identity-based equality/hash — candidates are tracked by object identity, never compared by value
class _Candidate:
    digest_item: DigestItem
    content_type: str
    content_id: int
    published_at: datetime
    technical_depth: Optional[int]
    content_category: Optional[str]
    topics: List[str] = field(default_factory=list)
    entity_ids: List[int] = field(default_factory=list)
    quality_score: float = 0.5
    embedding: Optional[list] = None
    reading_minutes: int = 1
    channel_id: Optional[str] = None  # YoutubeVideo.channel_id — only set for content_type="youtube_video"


class RankingService:
    """Computes one user's ranking against an already-fetched shared content pool."""

    def __init__(self, db) -> None:
        self.db = db

    def rank_for_user(
        self,
        recipient: Recipient,
        all_items: list,             # List[Article | YoutubeVideo] — the shared corpus, fetched ONCE by the caller
        source_categories: dict,
    ) -> Tuple[List[RankedArticle], Dict[str, DigestItem]]:
        """Returns (ranked_scores, item_map) — the exact shapes UserRankingRepository/EmailAgent expect."""
        user_id = recipient.user_id

        # M10: visibility='user' sources are private to subscribers (+
        # followers of a person whose registered footprint IS that source —
        # see _followed_person_footprints) — resolved BEFORE the eligibility
        # filter below so a person-follow's guaranteed-inclusion isn't
        # accidentally excluded here, then never given a chance to be
        # guaranteed back in later.
        followed_topics, followed_entities, followed_sources = self._followed_targets(user_id)
        followed_person_sources, followed_person_channels = self._followed_person_footprints(followed_entities)
        user_source_keys = self._user_visibility_source_keys()
        allowed_user_source_keys = self._subscribed_user_source_keys(user_id) | followed_person_sources

        eligible = [
            item for item in all_items
            if _article_type_of(item) not in recipient.excluded_sources
            and source_categories.get(_article_type_of(item)) not in recipient.excluded_categories
            and (_article_type_of(item) not in user_source_keys or _article_type_of(item) in allowed_user_source_keys)
        ]
        if not eligible:
            return [], {}

        candidates = self._build_candidates(eligible)
        if not candidates:
            return [], {}

        profile_vector = None
        if user_id is not None:
            pv = UserProfileVectorRepository(self.db).get_for_user(user_id)
            if pv is not None and pv.sample_size > 0:
                profile_vector = pv.vector

        cold_start_topics = self._onboarding_topic_slugs(user_id) if (profile_vector is None and user_id is not None) else set()

        pool = self._select_candidates(
            candidates, profile_vector, cold_start_topics, followed_topics, followed_entities, followed_sources,
            followed_person_sources, followed_person_channels,
        )
        if not pool:
            return [], {}

        topic_affinity, source_affinity = self._affinities(user_id)
        last_shown = DigestClickTokenRepository(self.db).get_last_shown_at(user_id, days=NOVELTY_LOOKBACK_DAYS) if user_id else {}

        now = datetime.now(timezone.utc)
        scored = [
            (c, self._score(
                c, topic_affinity, source_affinity, last_shown, recipient,
                cold_start_topics, followed_topics, followed_entities, followed_sources,
                followed_person_sources, followed_person_channels, now,
            ))
            for c in pool
        ]

        max_items = recipient.max_items or 10
        if max_items >= EXPLORATION_MIN_LIST_SIZE:
            exploration_count = max(1, round(max_items * EXPLORATION_FRACTION))
        else:
            exploration_count = 0
        relevance_count = max(0, max_items - exploration_count)

        chosen = self._mmr_select(scored, relevance_count)
        chosen_ids = {id(c) for c, _ in chosen}
        remaining = [cs for cs in scored if id(cs[0]) not in chosen_ids]
        chosen += self._exploration_pick(remaining, exploration_count)

        ranked_scores: List[RankedArticle] = []
        item_map: Dict[str, DigestItem] = {}
        for rank, (candidate, features) in enumerate(chosen, start=1):
            digest = candidate.digest_item
            item_map[digest.digest_id] = digest
            relevance_score = max(0.0, min(10.0, round(features["final_score"] * 10.0, 2)))
            ranked_scores.append(RankedArticle(
                digest_id=digest.digest_id,
                relevance_score=relevance_score,
                rank=rank,
                reasoning=_build_explanation(features),
                features=features,
            ))
        return ranked_scores, item_map

    # ------------------------------------------------------------------
    # Candidate assembly
    # ------------------------------------------------------------------

    def _build_candidates(self, items: list) -> List[_Candidate]:
        if not items:
            return []

        keys = [("article", i.id) if isinstance(i, Article) else ("youtube_video", i.id) for i in items]

        enrichment_by_key = {
            (e.content_type, e.content_id): e
            for e in self.db.query(ContentEnrichment)
            .filter(tuple_(ContentEnrichment.content_type, ContentEnrichment.content_id).in_(keys))
            .all()
        }
        score_by_key = {
            (ct, cid): score
            for ct, cid, score in self.db.query(ContentScore.content_type, ContentScore.content_id, ContentScore.score)
            .filter(tuple_(ContentScore.content_type, ContentScore.content_id).in_(keys))
            .all()
        }
        topics_by_key = defaultdict(list)
        for ct, cid, slug in (
            self.db.query(ContentTopic.content_type, ContentTopic.content_id, TaxonomyTopic.slug)
            .join(TaxonomyTopic, ContentTopic.taxonomy_topic_id == TaxonomyTopic.id)
            .filter(tuple_(ContentTopic.content_type, ContentTopic.content_id).in_(keys))
            .all()
        ):
            topics_by_key[(ct, cid)].append(slug)
        entities_by_key = defaultdict(list)
        for ct, cid, entity_id in (
            self.db.query(ContentEntity.content_type, ContentEntity.content_id, ContentEntity.entity_id)
            .filter(tuple_(ContentEntity.content_type, ContentEntity.content_id).in_(keys))
            .all()
        ):
            entities_by_key[(ct, cid)].append(entity_id)
        embedding_by_key = {
            (e.content_type, e.content_id): e.embedding
            for e in self.db.query(Embedding).filter(tuple_(Embedding.content_type, Embedding.content_id).in_(keys)).all()
        }

        candidates = []
        for item, key in zip(items, keys):
            content_type, content_id = key
            if isinstance(item, Article):
                digest_id = f"{item.source}:{item.id}"
                article_type = item.source
                reading_minutes = estimate_reading_minutes(len((item.content or "").split()))
            else:
                digest_id = f"youtube:{item.id}"
                article_type = "youtube"
                reading_minutes = estimate_watch_minutes(len((item.content or "").split()))

            enrichment = enrichment_by_key.get(key)
            candidates.append(_Candidate(
                digest_item=DigestItem(
                    digest_id=digest_id, title=item.title, summary=item.summary or "",
                    article_type=article_type, db_id=item.id,
                ),
                content_type=content_type,
                content_id=content_id,
                published_at=item.published_at,
                technical_depth=enrichment.technical_depth if enrichment else None,
                content_category=enrichment.content_category if enrichment else None,
                topics=topics_by_key.get(key, []),
                entity_ids=entities_by_key.get(key, []),
                quality_score=score_by_key.get(key, 0.5),
                embedding=embedding_by_key.get(key),
                reading_minutes=reading_minutes,
                channel_id=item.channel_id if isinstance(item, YoutubeVideo) else None,
            ))
        return candidates

    def _select_candidates(
        self, candidates, profile_vector, cold_start_topics, followed_topics, followed_entities, followed_sources,
        followed_person_sources, followed_person_channels,
    ) -> List[_Candidate]:
        by_key = {(c.content_type, c.content_id): c for c in candidates}
        selected_keys = set()

        # Leg A: recency
        for c in sorted(candidates, key=lambda c: c.published_at, reverse=True)[:RECENCY_CANDIDATE_LIMIT]:
            selected_keys.add((c.content_type, c.content_id))

        # Leg B: pgvector similarity to profile vector, or cold-start topic overlap
        if profile_vector is not None:
            for emb, _sim in EmbeddingRepository(self.db).find_similar(profile_vector, limit=SIMILARITY_CANDIDATE_LIMIT):
                key = (emb.content_type, emb.content_id)
                if key in by_key:
                    selected_keys.add(key)
        elif cold_start_topics:
            for c in candidates:
                if set(c.topics) & cold_start_topics:
                    selected_keys.add((c.content_type, c.content_id))

        # Leg C: followed entities/topics/sources — guaranteed inclusion,
        # even if an item is old or dissimilar to the profile vector.
        # M10: also guarantees a followed PERSON's own output (their blog/
        # YouTube channel via person_entities), independent of `entity_ids`
        # (content_entities mentions) — a person's own posts/videos rarely
        # mention them by name, so entity-mention matching alone would miss
        # most of their own content.
        if followed_topics or followed_entities or followed_sources or followed_person_sources or followed_person_channels:
            for c in candidates:
                key = (c.content_type, c.content_id)
                if key in selected_keys:
                    continue
                if (
                    (set(c.topics) & followed_topics)
                    or (set(str(e) for e in c.entity_ids) & followed_entities)
                    or (c.digest_item.article_type in followed_sources)
                    or (c.digest_item.article_type in followed_person_sources)
                    or (c.channel_id is not None and c.channel_id in followed_person_channels)
                ):
                    selected_keys.add(key)

        pool = [by_key[k] for k in selected_keys]
        if len(pool) > CANDIDATE_POOL_CAP:
            pool.sort(key=lambda c: c.published_at, reverse=True)
            pool = pool[:CANDIDATE_POOL_CAP]
        return pool

    # ------------------------------------------------------------------
    # Personalization inputs
    # ------------------------------------------------------------------

    def _affinities(self, user_id: Optional[int]) -> Tuple[Dict[str, float], Dict[str, float]]:
        if user_id is None:
            return {}, {}
        rows = (
            self.db.query(UserAffinity)
            .filter(UserAffinity.user_id == user_id, UserAffinity.dimension.in_(["topic", "source"]))
            .all()
        )
        topic = {r.key: r.weight for r in rows if r.dimension == "topic"}
        source = {r.key: r.weight for r in rows if r.dimension == "source"}
        return topic, source

    def _onboarding_topic_slugs(self, user_id: int) -> set:
        """Cold-start fallback (no profile vector yet): the taxonomy topics
        behind this user's onboarding Interest selections — two plain
        queries rather than one cross-declarative-base join, since
        DjangoInterest/DjangoUserInterest (DjangoBase) and TaxonomyTopic
        (this ORM's own Base) aren't in the same SQLAlchemy registry."""
        from app.database.models.django_readmodels import DjangoInterest, DjangoUserInterest, DjangoUserProfile

        topic_ids = [
            tid for (tid,) in
            self.db.query(DjangoInterest.taxonomy_topic_id)
            .join(DjangoUserInterest, DjangoUserInterest.interest_id == DjangoInterest.id)
            .join(DjangoUserProfile, DjangoUserProfile.id == DjangoUserInterest.profile_id)
            .filter(DjangoUserProfile.user_id == user_id, DjangoInterest.taxonomy_topic_id.isnot(None))
            .all()
        ]
        if not topic_ids:
            return set()
        return {slug for (slug,) in self.db.query(TaxonomyTopic.slug).filter(TaxonomyTopic.id.in_(topic_ids)).all()}

    def _followed_targets(self, user_id: Optional[int]) -> Tuple[set, set, set]:
        if user_id is None:
            return set(), set(), set()
        from app.database.models.django_readmodels import DjangoUserFollow

        rows = (
            self.db.query(DjangoUserFollow.target_type, DjangoUserFollow.target_key)
            .filter(DjangoUserFollow.user_id == user_id)
            .all()
        )
        topics = {key for t, key in rows if t == "topic"}
        entities = {key for t, key in rows if t == "entity"}
        sources = {key for t, key in rows if t == "source"}
        return topics, entities, sources

    def _followed_person_footprints(self, followed_entities: set) -> Tuple[set, set]:
        """
        M10: for every followed-entity id that's a person with a registered
        footprint (app/database/models/person_entity.py), resolve which
        Source.key values (blog/github/substack — each its own dedicated
        Source row) or YouTube channel_ids represent THEIR OWN content.
        YouTube is special-cased on channel_id rather than Source.key
        because every YouTube channel shares the single seeded
        key="youtube" Source row (one row, many channels in its config) —
        Source.key can't disambiguate one person's channel from another's.
        """
        entity_ids = [int(e) for e in followed_entities if e.isdigit()]
        if not entity_ids:
            return set(), set()

        from app.database.models.person_entity import PersonEntity
        from app.database.models.source import Source

        rows = (
            self.db.query(PersonEntity.footprint_type, PersonEntity.external_identifier, Source.key)
            .outerjoin(Source, PersonEntity.source_id == Source.id)
            .filter(PersonEntity.entity_id.in_(entity_ids))
            .all()
        )
        source_keys, channel_ids = set(), set()
        for footprint_type, external_identifier, source_key in rows:
            if footprint_type == "youtube":
                if external_identifier:
                    channel_ids.add(external_identifier)
            elif source_key:
                source_keys.add(source_key)
        return source_keys, channel_ids

    def _user_visibility_source_keys(self) -> set:
        """All Source.key values with visibility='user' — the set of sources gated by subscription, not exclusion (M10)."""
        return {key for (key,) in self.db.query(Source.key).filter(Source.visibility == "user").all()}

    def _subscribed_user_source_keys(self, user_id: Optional[int]) -> set:
        """
        Source.key values this user is subscribed to via Django's
        UserSourceSubscription (M10). Two plain queries, not one
        cross-declarative-base join — same reasoning as
        _onboarding_topic_slugs: DjangoUserSourceSubscription/
        DjangoUserProfile (DjangoBase) and Source (this ORM's own Base)
        aren't in the same SQLAlchemy registry.
        """
        if user_id is None:
            return set()
        from app.database.models.django_readmodels import DjangoUserProfile, DjangoUserSourceSubscription

        source_ids = [
            sid for (sid,) in
            self.db.query(DjangoUserSourceSubscription.source_id)
            .join(DjangoUserProfile, DjangoUserProfile.id == DjangoUserSourceSubscription.profile_id)
            .filter(DjangoUserProfile.user_id == user_id)
            .all()
        ]
        if not source_ids:
            return set()
        return {key for (key,) in self.db.query(Source.key).filter(Source.id.in_(source_ids)).all()}

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score(
        self, c: _Candidate, topic_affinity, source_affinity, last_shown, recipient: Recipient,
        cold_start_topics, followed_topics, followed_entities, followed_sources,
        followed_person_sources, followed_person_channels, now,
    ) -> dict:
        if topic_affinity:
            max_aff = max(topic_affinity.values())
            item_weights = [topic_affinity.get(t, 0.0) for t in c.topics]
            interest_score = (max(item_weights) / max_aff) if item_weights and max_aff > 0 else 0.0
        else:
            interest_score = 1.0 if (set(c.topics) & cold_start_topics) else 0.0

        quality = max(0.0, min(1.0, c.quality_score))

        age_hours = max(0.0, (now - c.published_at).total_seconds() / 3600.0)
        freshness = math.exp(-math.log(2) / FRESHNESS_HALFLIFE_HOURS * age_hours)

        if source_affinity:
            max_src = max(source_affinity.values())
            src_score = (source_affinity.get(c.digest_item.article_type, 0.0) / max_src) if max_src > 0 else 0.5
        else:
            src_score = 0.5

        shown_at = last_shown.get((c.content_type, c.content_id))
        if shown_at is None:
            novelty = 1.0
        else:
            age_days = max(0.0, (now - shown_at).total_seconds() / 86400.0)
            novelty = 1.0 - math.exp(-math.log(2) / NOVELTY_HALFLIFE_DAYS * age_days)

        base = (
            WEIGHTS["interest"] * interest_score
            + WEIGHTS["quality"] * quality
            + WEIGHTS["freshness"] * freshness
            + WEIGHTS["source_affinity"] * src_score
            + WEIGHTS["novelty"] * novelty
        )

        depth_mult = _depth_multiplier(c.technical_depth, recipient.profile.expertise_level)
        format_mult = _format_multiplier(c.digest_item.article_type, recipient.format_balance)
        lean_mult = _lean_multiplier(c.content_category, recipient.topic_lean)
        time_mult = _reading_time_multiplier(c.reading_minutes, recipient.reading_time_budget_minutes)

        final_score = max(0.0, min(1.0, base * depth_mult * format_mult * lean_mult * time_mult))

        matched_topics = sorted(
            set(c.topics) & (set(topic_affinity) | cold_start_topics),
            key=lambda t: -topic_affinity.get(t, 1.0),
        )

        is_person_own_content = (
            c.digest_item.article_type in followed_person_sources
            or (c.channel_id is not None and c.channel_id in followed_person_channels)
        )
        followed_match = None
        if is_person_own_content:
            followed_match = "a person you follow"
        elif set(c.topics) & followed_topics:
            followed_match = next(iter(set(c.topics) & followed_topics))
        elif set(str(e) for e in c.entity_ids) & followed_entities:
            followed_match = "an entity you follow"
        elif c.digest_item.article_type in followed_sources:
            followed_match = "a source you follow"

        return {
            "final_score": final_score,
            "interest_topic_score": round(interest_score, 4),
            "quality_score": round(quality, 4),
            "freshness": round(freshness, 4),
            "source_affinity": round(src_score, 4),
            "novelty": round(novelty, 4),
            "depth_multiplier": round(depth_mult, 4),
            "format_multiplier": round(format_mult, 4),
            "lean_multiplier": round(lean_mult, 4),
            "reading_time_multiplier": round(time_mult, 4),
            "matched_topics": matched_topics[:2],
            "followed_match": followed_match,
            "content_type": c.content_type,
            "content_id": c.content_id,
        }

    # ------------------------------------------------------------------
    # MMR diversification + exploration slice
    # ------------------------------------------------------------------

    def _mmr_select(self, scored: List[Tuple[_Candidate, dict]], count: int) -> List[Tuple[_Candidate, dict]]:
        if count <= 0 or not scored:
            return []
        pool = list(scored)
        selected: List[Tuple[_Candidate, dict]] = []
        selected_embeddings: List[list] = []

        while pool and len(selected) < count:
            best_idx, best_mmr = None, None
            for i, (candidate, features) in enumerate(pool):
                relevance = features["final_score"]
                if candidate.embedding is not None and selected_embeddings:
                    sim = max(_cosine_similarity(candidate.embedding, e) for e in selected_embeddings)
                else:
                    sim = 0.0
                mmr_score = MMR_LAMBDA * relevance - (1 - MMR_LAMBDA) * sim
                if best_mmr is None or mmr_score > best_mmr:
                    best_mmr, best_idx = mmr_score, i
            picked = pool.pop(best_idx)
            selected.append(picked)
            if picked[0].embedding is not None:
                selected_embeddings.append(picked[0].embedding)
        return selected

    def _exploration_pick(self, remaining: List[Tuple[_Candidate, dict]], count: int) -> List[Tuple[_Candidate, dict]]:
        """Weighted-random pick from the leftover pool — biased toward
        decent-but-not-top items, not pure noise, per the roadmap's mandatory
        10-15% exploration slice (filter-bubble mitigation)."""
        if count <= 0 or not remaining:
            return []
        pool = list(remaining)
        weights = [max(0.01, features["final_score"]) for _, features in pool]
        picks = []
        for _ in range(min(count, len(pool))):
            total = sum(weights)
            r = random.random() * total
            upto = 0.0
            for i, w in enumerate(weights):
                upto += w
                if upto >= r:
                    candidate, features = pool.pop(i)
                    weights.pop(i)
                    features = dict(features)
                    features["exploration_slot"] = True
                    picks.append((candidate, features))
                    break
        return picks


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _article_type_of(item) -> str:
    return "youtube" if isinstance(item, YoutubeVideo) else item.source


def _cosine_similarity(a, b) -> float:
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = math.sqrt(sum(float(x) * float(x) for x in a))
    norm_b = math.sqrt(sum(float(y) * float(y) for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _depth_multiplier(technical_depth: Optional[int], expertise_level: str) -> float:
    if technical_depth is None:
        return 1.0
    lo, hi = EXPERTISE_DEPTH_BANDS.get(expertise_level, (1, 5))
    if lo <= technical_depth <= hi:
        return 1.0
    distance = min(abs(technical_depth - lo), abs(technical_depth - hi))
    return max(0.6, 1.0 - 0.15 * distance)


def _format_multiplier(article_type: str, format_balance: str) -> float:
    is_video = article_type == "youtube"
    if format_balance == "videos":
        return 1.15 if is_video else 0.9
    if format_balance == "articles":
        return 1.15 if not is_video else 0.9
    return 1.0


def _lean_multiplier(content_category: Optional[str], topic_lean: str) -> float:
    if content_category is None or topic_lean == "balanced":
        return 1.0
    if topic_lean == "research":
        return 1.15 if content_category in RESEARCH_CATEGORIES else 0.95
    if topic_lean == "industry":
        return 1.15 if content_category in INDUSTRY_CATEGORIES else 0.95
    return 1.0


def _reading_time_multiplier(reading_minutes: int, budget_minutes: Optional[int]) -> float:
    if not budget_minutes or reading_minutes <= budget_minutes:
        return 1.0
    overage = reading_minutes - budget_minutes
    return max(0.5, 1.0 - 0.05 * overage)


def _build_explanation(features: dict) -> str:
    if features.get("exploration_slot"):
        return "A change of pace from your usual topics — worth a look."

    reasons = []
    if features.get("matched_topics"):
        reasons.append(f"matches your interest in {features['matched_topics'][0]}")
    if features.get("followed_match") == "a person you follow":
        reasons.append("is by a person you follow")
    elif features.get("followed_match"):
        reasons.append(f"related to {features['followed_match']}, which you follow")
    if features.get("source_affinity", 0) > 0.6:
        reasons.append("from a source you engage with often")
    if features.get("freshness", 0) > 0.7:
        reasons.append("published recently")
    if features.get("quality_score", 0) > 0.75:
        reasons.append("a high-quality item")

    if not reasons:
        return "Selected based on overall relevance to your profile."
    if len(reasons) == 1:
        return f"Recommended because it {reasons[0]}."
    return "Recommended because it " + ", ".join(reasons[:-1]) + f", and {reasons[-1]}."
