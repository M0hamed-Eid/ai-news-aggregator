# app/database/base.py
#
# Why a separate base.py?
# -----------------------
# SQLAlchemy needs one "DeclarativeBase" object that ALL models inherit from.
# Keeping it in its own tiny file breaks the circular-import problem:
#
#   session.py  imports  Base  from  base.py     ✓
#   models/*.py import   Base  from  base.py     ✓
#   session.py  does NOT import from models/     ✓  (no cycle)
#
# If you put Base inside session.py and then imported session in a model,
# you would get a circular import and Python would crash at startup.

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Every SQLAlchemy model in this project must inherit from this class.

    Example:
        from app.database.base import Base

        class Article(Base):
            __tablename__ = "articles"
            ...
    """
    pass