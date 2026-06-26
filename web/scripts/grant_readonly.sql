-- =============================================================================
-- OPTIONAL HARDENING (defense in depth) — Milestone 2
--
-- The Django code already cannot write or migrate the pipeline tables
-- (managed=False + PipelineRouter.allow_migrate=False + ReadOnly mixin).
-- This script adds a SECOND, database-enforced guarantee: a dedicated login
-- role that PHYSICALLY cannot write `articles` / `youtube_videos`, even if the
-- application code were changed.
--
-- Run as a superuser (e.g. the postgres user) against the ai_news database:
--   docker exec -i ai_news_db psql -U ai_news_user -d ai_news < grant_readonly.sql
-- Then point web/.env DATABASE_URL at the django_app role.
-- =============================================================================

-- 1. Dedicated application role for Django (change the password!).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'django_app') THEN
        CREATE ROLE django_app LOGIN PASSWORD 'change_this_password';
    END IF;
END
$$;

-- 2. Allow it to connect and use the public schema.
GRANT CONNECT ON DATABASE ai_news TO django_app;
GRANT USAGE ON SCHEMA public TO django_app;

-- 3. READ-ONLY on the pipeline-owned tables. No INSERT/UPDATE/DELETE.
GRANT SELECT ON public.articles        TO django_app;
GRANT SELECT ON public.youtube_videos  TO django_app;

-- 4. FULL access to Django-owned tables so migrations + auth keep working.
--    These were created by ai_news_user in Milestone 1; hand them to django_app.
ALTER TABLE public.users OWNER TO django_app;
-- Repeat ALTER TABLE ... OWNER TO django_app for each Django table, or grant:
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO django_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO django_app;
-- ...then REVOKE writes on the two pipeline tables to be explicit:
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.articles       FROM django_app;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.youtube_videos FROM django_app;

-- 5. Make future Django tables default to django_app ownership.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO django_app;

-- Verify (should show only SELECT for django_app on the pipeline tables):
--   \dp public.articles
--   \dp public.youtube_videos
