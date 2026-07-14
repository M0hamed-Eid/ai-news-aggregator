from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Load .env BEFORE resolving the DB URL below — mirrors app/database/session.py
# and run_pipeline.py's existing pattern.
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the DB URL via the SAME shared helper the running app uses
# (app/database/db_url.py) so the migration tool can never independently
# drift from the app on which database it targets.
from app.database.db_url import build_database_url

config.set_main_option("sqlalchemy.url", build_database_url())

# Import Base + every model module so they register on Base.metadata — this
# is deliberately the narrow `app.database.models` package, not the wider
# `app.database` package (which also pulls in `repositories`, unneeded here).
from app.database.base import Base
import app.database.models  # noqa: F401

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """
    Confirmed live (2026-07-14): autogenerate reflects EVERY table in the
    shared Postgres DB and diffs it against target_metadata, regardless of
    which SQLAlchemy Base it conceptually belongs to. Django owns tables
    (users, user_profiles, personas, ...) that live in this same DB but are
    NOT registered on Base.metadata (they're on a separate DjangoBase in
    app/database/models/django_readmodels.py, read-only mirrors). Without
    this filter, autogenerate proposes DROPPING every Django-owned table on
    the very first baseline run — exactly the footgun the roadmap warned
    about. Exclude any reflected table with no corresponding table in our
    own metadata: this Alembic instance manages pipeline tables only, full
    stop, never anything it didn't itself register.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
