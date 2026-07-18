# app/database/models/__init__.py
#
# Re-export every model so callers can do:
#
#   from app.database.models import Article, YoutubeVideo
#
# More importantly, importing this package causes Python to execute every
# model file, which registers each model class with SQLAlchemy's MetaData.
# This is required BEFORE calling Base.metadata.create_all().

from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo
from app.database.models.embedding import Embedding
from app.database.models.source import Source
from app.database.models.user_ranking import UserRanking
from app.database.models.digest_log import DigestLog
from app.database.models.user_affinity import UserAffinity
from app.database.models.digest_click_token import DigestClickToken
from app.database.models.taxonomy_topic import TaxonomyTopic
from app.database.models.content_topic import ContentTopic
from app.database.models.entity import Entity
from app.database.models.content_entity import ContentEntity
from app.database.models.content_cluster import ContentCluster
from app.database.models.content_cluster_member import ContentClusterMember
from app.database.models.content_enrichment import ContentEnrichment
from app.database.models.content_score import ContentScore
from app.database.models.user_profile_vector import UserProfileVector
from app.database.models.person_entity import PersonEntity
from app.database.models.trend import Trend
from app.database.models.trend_report import TrendReport
from app.database.models.content_chunk import ContentChunk
from app.database.models.stt_job import SttJob

__all__ = [
    "Article", "YoutubeVideo", "Embedding", "Source", "UserRanking", "DigestLog",
    "UserAffinity", "DigestClickToken",
    "TaxonomyTopic", "ContentTopic", "Entity", "ContentEntity",
    "ContentCluster", "ContentClusterMember", "ContentEnrichment", "ContentScore",
    "UserProfileVector", "PersonEntity", "Trend", "TrendReport",
    "ContentChunk", "SttJob",
]