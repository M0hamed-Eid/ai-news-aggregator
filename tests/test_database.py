# tests/test_database.py
#
# Tests for the database layer — models, repositories, and session management.
#
# These tests use an IN-MEMORY SQLite database so they:
#   - Run without a running PostgreSQL instance
#   - Are fast (< 1 second)
#   - Are safe to run in CI
#
# IMPORTANT: PostgreSQL-specific features (ON CONFLICT, partial indexes) are
# NOT available in SQLite. The bulk_create tests are therefore skipped here.
# To test ON CONFLICT behaviour, use the integration tests with a real PG DB.
#
# Run:  pytest tests/test_database.py -v

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo
from app.scrapers.base_scraper import ScrapedArticle


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def db_session():
    """
    Provide a fresh in-memory SQLite session for each test.
    Tables are created before the test and dropped afterward — completely isolated.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # SQLite doesn't enforce CHECK constraints by default.
    # This pragma turns them on so our constraint tests work.
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _make_scraped_article(
    title="Test Article",
    url="https://openai.com/news/test-article",
    source="blog_openai",
    author="OpenAI",
    content="This is a long enough article content with more than 50 chars.",
    video_id=None,
) -> ScrapedArticle:
    return ScrapedArticle(
        title=title,
        url=url,
        content=content,
        source=source,
        channel_or_author=author,
        published_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        video_id=video_id,
    )


def _make_scraped_video(
    title="Test Video",
    url="https://youtube.com/watch?v=abc123",
    video_id="abc123",
    channel="Andrej Karpathy",
) -> ScrapedArticle:
    return ScrapedArticle(
        title=title,
        url=url,
        content="This is the video transcript with more than 50 characters total.",
        source="youtube",
        channel_or_author=channel,
        published_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        video_id=video_id,
    )


# =============================================================================
# Model tests
# =============================================================================

class TestArticleModel:

    def test_create_article_directly(self, db_session):
        article = Article(
            title="Hello World",
            url="https://openai.com/news/hello",
            source="blog_openai",
            author="OpenAI",
            content="Some content here that is long enough.",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(article)
        db_session.commit()

        assert article.id is not None
        assert article.id > 0

    def test_article_url_is_unique(self, db_session):
        """Inserting two articles with the same URL should raise an IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        url = "https://openai.com/news/duplicate"
        for _ in range(2):
            db_session.add(Article(
                title="Dup", url=url, source="blog_openai",
                author="OpenAI", content="x" * 60,
                published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ))

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_article_to_dict(self, db_session):
        article = Article(
            title="Dict Test",
            url="https://openai.com/news/dict",
            source="blog_openai",
            author="OpenAI",
            content="x" * 60,
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(article)
        db_session.commit()

        d = article.to_dict()
        assert d["title"] == "Dict Test"
        assert d["source"] == "blog_openai"
        assert "published_at" in d

    def test_created_at_is_set_automatically(self, db_session):
        article = Article(
            title="Timestamp Test",
            url="https://openai.com/news/ts",
            source="blog_openai",
            author="OpenAI",
            content="x" * 60,
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(article)
        db_session.commit()
        db_session.refresh(article)

        # created_at is set by server_default — it should be a datetime
        assert article.created_at is not None


class TestYoutubeVideoModel:

    def test_create_video(self, db_session):
        video = YoutubeVideo(
            video_id="abc123xyz",
            channel_name="Andrej Karpathy",
            title="Neural Networks from Scratch",
            url="https://youtube.com/watch?v=abc123xyz",
            source="youtube",
            content="transcript text " * 10,
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add(video)
        db_session.commit()

        assert video.id is not None

    def test_video_id_is_unique(self, db_session):
        from sqlalchemy.exc import IntegrityError

        for _ in range(2):
            db_session.add(YoutubeVideo(
                video_id="dupvideo1",
                channel_name="Channel",
                title="Dup",
                url=f"https://youtube.com/watch?v=dupvideo{_}",
                source="youtube",
                published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            ))

        with pytest.raises(IntegrityError):
            db_session.commit()


# =============================================================================
# Repository tests
# =============================================================================

class TestArticleRepository:

    def test_create_returns_article(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo    = ArticleRepository(db_session)
        scraped = _make_scraped_article()
        article = repo.create(scraped)

        assert article is not None
        assert isinstance(article, Article)
        assert article.id is not None
        db_session.commit()

    def test_create_duplicate_returns_none(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo    = ArticleRepository(db_session)
        scraped = _make_scraped_article()

        first  = repo.create(scraped)
        db_session.commit()

        second = repo.create(scraped)   # same URL

        assert first  is not None
        assert second is None           # duplicate — should be skipped

    def test_exists_by_url(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo    = ArticleRepository(db_session)
        scraped = _make_scraped_article(url="https://openai.com/news/unique123")

        assert repo.exists_by_url(scraped.url) is False
        repo.create(scraped)
        db_session.commit()
        assert repo.exists_by_url(scraped.url) is True

    def test_get_by_url(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo    = ArticleRepository(db_session)
        scraped = _make_scraped_article(url="https://openai.com/news/getbyurl")
        repo.create(scraped)
        db_session.commit()

        found = repo.get_by_url(scraped.url)
        assert found is not None
        assert found.url == scraped.url

    def test_get_by_url_not_found(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo  = ArticleRepository(db_session)
        found = repo.get_by_url("https://does-not-exist.com")
        assert found is None

    def test_count(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo = ArticleRepository(db_session)
        assert repo.count() == 0

        for i in range(3):
            repo.create(_make_scraped_article(url=f"https://openai.com/news/item{i}"))
        db_session.commit()

        assert repo.count() == 3

    def test_update_summary(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo    = ArticleRepository(db_session)
        scraped = _make_scraped_article(url="https://openai.com/news/summary")
        article = repo.create(scraped)
        db_session.commit()

        success = repo.update_summary(article.id, "Great summary", "LLM,agents")
        db_session.commit()

        assert success is True
        db_session.refresh(article)
        assert article.summary == "Great summary"
        assert article.tags    == "LLM,agents"

    def test_get_unsummarised(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo = ArticleRepository(db_session)
        for i in range(3):
            repo.create(_make_scraped_article(url=f"https://openai.com/news/us{i}"))
        db_session.commit()

        unsummarised = repo.get_unsummarised(limit=10)
        assert len(unsummarised) == 3

    def test_get_by_id_returns_none_for_missing(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo = ArticleRepository(db_session)
        assert repo.get_by_id(99999) is None

    def test_delete(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo    = ArticleRepository(db_session)
        scraped = _make_scraped_article(url="https://openai.com/news/delete_me")
        article = repo.create(scraped)
        db_session.commit()

        deleted = repo.delete(article.id)
        db_session.commit()

        assert deleted is True
        assert repo.get_by_id(article.id) is None

    def test_get_by_source(self, db_session):
        from app.database.repositories.article_repository import ArticleRepository

        repo = ArticleRepository(db_session)
        repo.create(_make_scraped_article(url="https://openai.com/1", source="blog_openai"))
        repo.create(_make_scraped_article(url="https://anthropic.com/1", source="blog_anthropic"))
        db_session.commit()

        openai_articles = repo.get_by_source("blog_openai")
        assert len(openai_articles) == 1
        assert openai_articles[0].source == "blog_openai"


class TestYoutubeRepository:

    def test_create_video(self, db_session):
        from app.database.repositories.youtube_repository import YoutubeRepository

        repo    = YoutubeRepository(db_session)
        scraped = _make_scraped_video()
        video   = repo.create(scraped)
        db_session.commit()

        assert video is not None
        assert video.id is not None
        assert video.video_id == "abc123"

    def test_create_duplicate_returns_none(self, db_session):
        from app.database.repositories.youtube_repository import YoutubeRepository

        repo    = YoutubeRepository(db_session)
        scraped = _make_scraped_video()

        first  = repo.create(scraped)
        db_session.commit()
        second = repo.create(scraped)

        assert first  is not None
        assert second is None

    def test_exists_by_video_id(self, db_session):
        from app.database.repositories.youtube_repository import YoutubeRepository

        repo    = YoutubeRepository(db_session)
        scraped = _make_scraped_video(video_id="testid999")

        assert repo.exists_by_video_id("testid999") is False
        repo.create(scraped)
        db_session.commit()
        assert repo.exists_by_video_id("testid999") is True

    def test_get_by_channel(self, db_session):
        from app.database.repositories.youtube_repository import YoutubeRepository

        repo = YoutubeRepository(db_session)
        repo.create(_make_scraped_video(video_id="v1", channel="Chan A", url="https://yt.com/v1"))
        repo.create(_make_scraped_video(video_id="v2", channel="Chan B", url="https://yt.com/v2"))
        db_session.commit()

        results = repo.get_by_channel("Chan A")
        assert len(results) == 1
        assert results[0].channel_name == "Chan A"

    def test_get_unsummarised_excludes_empty_content(self, db_session):
        from app.database.repositories.youtube_repository import YoutubeRepository

        repo = YoutubeRepository(db_session)
        # Video with content
        v1 = YoutubeVideo(
            video_id="has_content",
            channel_name="X",
            title="T",
            url="https://yt.com/has",
            source="youtube",
            content="transcript text " * 5,
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        # Video WITHOUT content (no transcript)
        v2 = YoutubeVideo(
            video_id="no_content",
            channel_name="X",
            title="T2",
            url="https://yt.com/no",
            source="youtube",
            content=None,
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db_session.add_all([v1, v2])
        db_session.commit()

        unsummarised = repo.get_unsummarised(limit=10)
        video_ids = [v.video_id for v in unsummarised]
        assert "has_content" in video_ids
        assert "no_content" not in video_ids   # excluded because content IS NULL


# =============================================================================
# Session / connection tests
# =============================================================================

class TestSessionContextManager:

    def test_get_db_session_commits_on_success(self):
        """
        We can't use the real DB here, but we can verify the context manager
        calls commit() on a successful block and close() always.
        """
        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)

        # Patch SessionLocal inside session module
        import app.database.session as session_module
        original = session_module.SessionLocal
        session_module.SessionLocal = mock_factory

        try:
            from app.database.session import get_db_session
            with get_db_session() as db:
                assert db is mock_session

            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()
            mock_session.rollback.assert_not_called()
        finally:
            session_module.SessionLocal = original

    def test_get_db_session_rollback_on_exception(self):
        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)

        import app.database.session as session_module
        original = session_module.SessionLocal
        session_module.SessionLocal = mock_factory

        try:
            from app.database.session import get_db_session
            with pytest.raises(ValueError):
                with get_db_session():
                    raise ValueError("simulated DB error")

            mock_session.rollback.assert_called_once()
            mock_session.commit.assert_not_called()
            mock_session.close.assert_called_once()
        finally:
            session_module.SessionLocal = original