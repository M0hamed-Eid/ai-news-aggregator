# app/database/models/entity.py
#
# Deduplicated named entities mentioned across content (M8): companies, AI
# models, people, technologies. Uniqueness is (name, entity_type) — v1 scope
# deliberately does NOT canonicalize near-duplicates ("OpenAI" vs "Open AI");
# that's a later-milestone refinement, not M8's job.

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="'company' | 'model' | 'person' | 'technology'",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("name", "entity_type", name="uq_entity_name_type"),
        CheckConstraint(
            "entity_type IN ('company', 'model', 'person', 'technology')",
            name="ck_entities_entity_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<Entity name={self.name!r} type={self.entity_type!r}>"
