"""
Database routing for the shared PostgreSQL.

Single physical database, two ownership domains:

* `catalog`  — pipeline-owned tables (articles, youtube_videos). READ ONLY.
* everything else — Django-owned tables (users, auth_*, django_*). READ/WRITE.

The critical guarantee here is `allow_migrate`: Django will NEVER run a
migration (CREATE/ALTER/DROP) against a pipeline-owned table, even if someone
accidentally flips a model to managed=True.
"""


class PipelineRouter:
    pipeline_apps = {"catalog"}

    def db_for_read(self, model, **hints):
        return "default"

    def db_for_write(self, model, **hints):
        # Writes still resolve to the default DB, but the catalog models block
        # save()/delete() at the ORM level (see apps.catalog.models.ReadOnly).
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.pipeline_apps:
            # Never migrate pipeline-owned tables from Django.
            return False
        return True
