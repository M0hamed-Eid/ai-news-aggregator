# app/database/seed_taxonomy_topics.py
#
# Backfills the controlled topic vocabulary (app/database/models/taxonomy_topic.py)
# with ~27 rows. Idempotent upsert-by-slug — safe to re-run any time. The
# first 15 slugs are IDENTICAL to web/apps/onboarding's seeded Interest rows
# on purpose — Django's Interest.taxonomy_topic FK is matched by slug in a
# data migration (web/apps/onboarding/migrations/000X_link_taxonomy_topics.py)
# so user interests and content topics share ONE vocabulary, per the roadmap.
# The remaining ~12 are content-classification-only — too granular/technical
# for a user-facing "thing to follow" chip, but valid EnrichmentAgent targets.
#
# Usage:
#   python -m app.database.seed_taxonomy_topics

import logging

logging.basicConfig(
    level="INFO",
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# The ~27 seed rows: (slug, name, category, sort_order)
# =============================================================================
# The first 15 match web/apps/onboarding/migrations/0002_seed_lookups.py's
# INTERESTS list exactly (slug + sort_order) — do not rename/reorder these
# without also updating that file and the Interest-linking data migration.

SEED_TAXONOMY_TOPICS = [
    # --- Shared with Django's Interest vocabulary (slugs must match exactly) ---
    ("large-language-models",   "Large Language Models",     "core-ai",       1),
    ("ai-agents",               "AI Agents",                 "core-ai",       2),
    ("open-source-models",      "Open Source Models",        "core-ai",       3),
    ("nlp",                     "NLP",                        "core-ai",       4),
    ("ml-research",             "Machine Learning Research", "core-ai",       5),
    ("rag-vector-databases",    "RAG & Vector Databases",    "core-ai",       6),
    ("computer-vision",         "Computer Vision",           "core-ai",       7),
    ("reinforcement-learning",  "Reinforcement Learning",    "core-ai",       8),
    ("ai-safety",               "AI Safety & Alignment",     "policy",        9),
    ("ai-policy",               "AI Policy & Regulation",    "policy",       10),
    ("robotics",                "Robotics",                  "applications", 11),
    ("mlops",                   "MLOps & Infrastructure",    "applications", 12),
    ("startups-funding",        "Startups & Funding",        "business",     13),
    ("developer-tools",         "Developer Tools",           "applications", 14),
    ("multimodal-ai",           "Multimodal AI",             "core-ai",      15),
    # --- Content-classification-only additions (no Interest counterpart) ---
    ("model-releases",          "Model Releases",            "core-ai",      16),
    ("benchmarks-evaluation",   "Benchmarks & Evaluation",   "core-ai",      17),
    ("ai-hardware-chips",       "AI Hardware & Chips",       "infrastructure", 18),
    ("cloud-ai-infrastructure", "Cloud AI Infrastructure",   "infrastructure", 19),
    ("enterprise-ai",           "Enterprise AI",             "business",     20),
    ("generative-media",        "Generative Media",          "applications", 21),
    ("coding-assistants",       "Coding Assistants",         "applications", 22),
    ("ai-in-science",           "AI in Science",             "applications", 23),
    ("data-privacy-security",   "Data Privacy & Security",   "policy",       24),
    ("open-source-tooling",     "Open Source Tooling",       "applications", 25),
    ("ai-education",            "AI Education",              "applications", 26),
    ("industry-news-general",   "Industry News (General)",  "business",     27),
]


def seed_taxonomy_topics() -> None:
    """
    Upsert every row in SEED_TAXONOMY_TOPICS by slug. Safe to re-run — never
    duplicates rows, never touches is_active on existing rows (runtime state,
    not seed data).
    """
    from app.database.session import get_db_session
    from app.database.repositories.taxonomy_topic_repository import TaxonomyTopicRepository
    from app.database.models.taxonomy_topic import TaxonomyTopic

    created, updated = 0, 0

    with get_db_session() as db:
        repo = TaxonomyTopicRepository(db)

        for slug, name, category, sort_order in SEED_TAXONOMY_TOPICS:
            existing = repo.get_by_slug(slug)
            if existing is not None:
                existing.name = name
                existing.category = category
                existing.sort_order = sort_order
                logger.info(f"Updated taxonomy topic: {slug}")
                updated += 1
            else:
                db.add(TaxonomyTopic(slug=slug, name=name, category=category, sort_order=sort_order))
                logger.info(f"Created taxonomy topic: {slug}")
                created += 1

    logger.info(f"Seed complete. created={created} updated={updated} total={len(SEED_TAXONOMY_TOPICS)}")


if __name__ == "__main__":
    seed_taxonomy_topics()
