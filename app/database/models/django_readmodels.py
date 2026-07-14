# app/database/models/django_readmodels.py
#
# READ-ONLY mirror of Django's user/personalization tables (web/apps/accounts,
# web/apps/onboarding) for the SQLAlchemy pipeline to read at digest-generation
# time. Django owns and migrates these tables (same physical Postgres, shared
# by both processes — confirmed both .env files point at 127.0.0.1:5433/ai_news).
#
# This is the exact inverse of web/apps/catalog's managed=False mirror of
# Article/YoutubeVideo (Django reading SQLAlchemy's tables, read-only) —
# applied in the other direction (SQLAlchemy reading Django's tables, read-only).
#
# CRITICAL: these classes use a SEPARATE DeclarativeBase (DjangoBase), NOT the
# shared `Base` from app/database/base.py. This is deliberate — app/database/
# create_tables.py only ever calls Base.metadata.create_all(), and if these
# classes were registered on that same Base, create_all() would try to CREATE
# these tables too. Django already creates/migrates them; the pipeline must
# never attempt to create, alter, or write through these classes — read-only,
# always.
#
# Schema drift risk: if Django's models change (new/renamed columns, new
# tables), this file will NOT know automatically — there is no sync mechanism
# between the two ORMs. Update this file to match whenever
# web/apps/accounts/models.py or web/apps/onboarding/models.py change.

from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class DjangoBase(DeclarativeBase):
    """Separate from app.database.base.Base on purpose — never passed to create_tables.py."""
    pass


class DjangoUser(DjangoBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    first_name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean)

    profile: Mapped[Optional["DjangoUserProfile"]] = relationship(
        back_populates="user", uselist=False
    )


class DjangoPersona(DjangoBase):
    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))


class DjangoInterest(DjangoBase):
    __tablename__ = "interests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class DjangoUserProfile(DjangoBase):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    persona_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("personas.id"), nullable=True
    )
    onboarding_completed: Mapped[bool] = mapped_column(Boolean)

    user: Mapped["DjangoUser"] = relationship(back_populates="profile")
    persona: Mapped[Optional["DjangoPersona"]] = relationship()
    interests: Mapped[List["DjangoUserInterest"]] = relationship(back_populates="profile")
    digest_settings: Mapped[Optional["DjangoUserDigestSettings"]] = relationship(
        back_populates="profile", uselist=False
    )
    exclusions: Mapped[List["DjangoUserExclusion"]] = relationship(back_populates="profile")


class DjangoUserInterest(DjangoBase):
    __tablename__ = "user_interests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_profiles.id"))
    interest_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("interests.id"))
    weight: Mapped[float] = mapped_column(Float)

    profile: Mapped["DjangoUserProfile"] = relationship(back_populates="interests")
    interest: Mapped["DjangoInterest"] = relationship()


class DjangoUserDigestSettings(DjangoBase):
    __tablename__ = "user_digest_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_profiles.id"))
    frequency: Mapped[str] = mapped_column(String(20))
    max_items: Mapped[int] = mapped_column(BigInteger)
    is_paused: Mapped[bool] = mapped_column(Boolean)
    expertise_level: Mapped[str] = mapped_column(String(20))
    content_depth: Mapped[str] = mapped_column(String(20))

    profile: Mapped["DjangoUserProfile"] = relationship(back_populates="digest_settings")


class DjangoUserExclusion(DjangoBase):
    __tablename__ = "user_exclusions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    profile_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_profiles.id"))
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(100))

    profile: Mapped["DjangoUserProfile"] = relationship(back_populates="exclusions")
