# app/database/repositories/__init__.py

from app.database.repositories.article_repository import ArticleRepository
from app.database.repositories.youtube_repository import YoutubeRepository
from app.database.repositories.embedding_repository import EmbeddingRepository
from app.database.repositories.source_repository import SourceRepository
from app.database.repositories.user_ranking_repository import UserRankingRepository
from app.database.repositories.digest_log_repository import DigestLogRepository
from app.database.repositories.digest_click_token_repository import DigestClickTokenRepository
from app.database.repositories.user_affinity_repository import UserAffinityRepository
from app.database.repositories.taxonomy_topic_repository import TaxonomyTopicRepository
from app.database.repositories.content_topic_repository import ContentTopicRepository
from app.database.repositories.entity_repository import EntityRepository
from app.database.repositories.content_entity_repository import ContentEntityRepository
from app.database.repositories.content_cluster_repository import ContentClusterRepository
from app.database.repositories.content_enrichment_repository import ContentEnrichmentRepository
from app.database.repositories.content_score_repository import ContentScoreRepository

__all__ = [
    "ArticleRepository", "YoutubeRepository", "EmbeddingRepository",
    "SourceRepository", "UserRankingRepository", "DigestLogRepository",
    "DigestClickTokenRepository", "UserAffinityRepository",
    "TaxonomyTopicRepository", "ContentTopicRepository", "EntityRepository",
    "ContentEntityRepository", "ContentClusterRepository",
    "ContentEnrichmentRepository", "ContentScoreRepository",
]