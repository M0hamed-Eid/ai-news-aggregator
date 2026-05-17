# app/database/__init__.py
#
# Public API for the database package.
# Other parts of the app import from here — they don't need to know
# which submodule something lives in.

from app.database.session import get_db_session, check_database_connection
from app.database.models  import Article, YoutubeVideo
from app.database.repositories import ArticleRepository, YoutubeRepository

__all__ = [
    "get_db_session",
    "check_database_connection",
    "Article",
    "YoutubeVideo",
    "ArticleRepository",
    "YoutubeRepository",
]