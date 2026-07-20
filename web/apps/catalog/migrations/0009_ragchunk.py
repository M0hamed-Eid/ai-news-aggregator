# RagChunk read-only mirror of the pipeline-owned `rag_chunks` table (M14).
# Pure Django bookkeeping — managed=False + PipelineRouter.allow_migrate=False
# for the catalog app means this issues NO DDL (the table is created/owned by
# the pipeline's Alembic migration f3a9c1d20e77). Mirrors 0005_embedding.py.
import apps.catalog.models
import pgvector.django.vector
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0008_contentchunk_sttjob'),
    ]

    operations = [
        migrations.CreateModel(
            name='RagChunk',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('content_type', models.CharField(max_length=20)),
                ('content_id', models.BigIntegerField()),
                ('chunk_index', models.IntegerField()),
                ('text', models.TextField()),
                ('char_start', models.IntegerField(blank=True, null=True)),
                ('char_end', models.IntegerField(blank=True, null=True)),
                ('start_seconds', models.FloatField(blank=True, null=True)),
                ('end_seconds', models.FloatField(blank=True, null=True)),
                ('token_count', models.IntegerField(blank=True, null=True)),
                ('embedding', pgvector.django.vector.VectorField(dimensions=384)),
                ('index_version', models.CharField(max_length=40)),
                ('created_at', models.DateTimeField()),
            ],
            options={
                'verbose_name': 'rag chunk',
                'verbose_name_plural': 'rag chunks',
                'db_table': 'rag_chunks',
                'ordering': ['content_type', 'content_id', 'chunk_index'],
                'managed': False,
            },
            bases=(apps.catalog.models.ReadOnly, models.Model),
        ),
    ]
