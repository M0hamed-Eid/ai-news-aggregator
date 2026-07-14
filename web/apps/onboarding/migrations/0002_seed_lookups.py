"""Seed the fixed lookup tables: Persona (7 rows) and Interest (15 rows)."""
from django.db import migrations

PERSONAS = [
    # (slug, name, sort_order)
    ("student", "Student", 1),
    ("researcher", "Researcher", 2),
    ("engineer", "Engineer / Developer", 3),
    ("product_manager", "Product Manager", 4),
    ("executive", "Executive / Leader", 5),
    ("founder", "Founder / Entrepreneur", 6),
    ("hobbyist", "Hobbyist / Enthusiast", 7),
]

INTERESTS = [
    # (slug, name, category, sort_order)
    ("large-language-models", "Large Language Models", "core-ai", 1),
    ("ai-agents", "AI Agents", "core-ai", 2),
    ("open-source-models", "Open Source Models", "core-ai", 3),
    ("nlp", "NLP", "core-ai", 4),
    ("ml-research", "Machine Learning Research", "core-ai", 5),
    ("rag-vector-databases", "RAG & Vector Databases", "core-ai", 6),
    ("computer-vision", "Computer Vision", "core-ai", 7),
    ("reinforcement-learning", "Reinforcement Learning", "core-ai", 8),
    ("ai-safety", "AI Safety & Alignment", "policy", 9),
    ("ai-policy", "AI Policy & Regulation", "policy", 10),
    ("robotics", "Robotics", "applications", 11),
    ("mlops", "MLOps & Infrastructure", "applications", 12),
    ("startups-funding", "Startups & Funding", "business", 13),
    ("developer-tools", "Developer Tools", "applications", 14),
    ("multimodal-ai", "Multimodal AI", "core-ai", 15),
]


def seed_lookups(apps, schema_editor):
    Persona = apps.get_model("onboarding", "Persona")
    Interest = apps.get_model("onboarding", "Interest")

    for slug, name, sort_order in PERSONAS:
        Persona.objects.update_or_create(
            slug=slug, defaults={"name": name, "sort_order": sort_order}
        )

    for slug, name, category, sort_order in INTERESTS:
        Interest.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "category": category, "sort_order": sort_order},
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("onboarding", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_lookups, noop_reverse),
    ]
