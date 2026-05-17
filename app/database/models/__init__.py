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

__all__ = ["Article", "YoutubeVideo"]