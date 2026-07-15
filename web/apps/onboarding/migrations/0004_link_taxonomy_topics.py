"""
Link Interest.taxonomy_topic by matching slug against the pipeline-owned
taxonomy_topics table (mirrored read-only as catalog.TaxonomyTopic).

PREREQUISITE: this migration only links rows that already exist in
taxonomy_topics at the time it runs — the pipeline's Alembic migration +
`python -m app.database.seed_taxonomy_topics` MUST have already been run
against the same shared dev DB before this migration runs (Django's own
migration graph cannot express or enforce that cross-process dependency).
If run too early, every Interest.taxonomy_topic_id is silently left null —
safe to re-run this migration's forward function again later once the
pipeline side is seeded (RunPython re-runs are not automatic; re-run via
`manage.py migrate onboarding 0003 && manage.py migrate onboarding` or a
one-off shell command).
"""
from django.db import migrations


def link_taxonomy_topics(apps, schema_editor):
    Interest = apps.get_model("onboarding", "Interest")
    TaxonomyTopic = apps.get_model("catalog", "TaxonomyTopic")

    linked = 0
    for interest in Interest.objects.all():
        topic = TaxonomyTopic.objects.filter(slug=interest.slug).first()
        if topic is not None:
            interest.taxonomy_topic_id = topic.id
            interest.save(update_fields=["taxonomy_topic"])
            linked += 1

    print(f"  Linked {linked}/{Interest.objects.count()} Interest rows to taxonomy_topics by slug.")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("onboarding", "0003_interest_taxonomy_topic"),
        ("catalog", "0004_contentcluster_contentclustermember_and_more"),
    ]

    operations = [
        migrations.RunPython(link_taxonomy_topics, noop_reverse),
    ]
