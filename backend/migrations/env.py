import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from backend.app.services import database


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Models are introduced with the repository migration. The initial revision owns
# the current schema explicitly so Alembic does not infer changes from SQLite.
target_metadata = None


def get_migration_database_url() -> str:
    """Return the direct PostgreSQL URL reserved for schema migrations."""
    database_url = os.getenv("MIGRATION_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "MIGRATION_DATABASE_URL must be set to a direct PostgreSQL connection URL."
        )

    try:
        return database.validate_migration_database_url(database_url)
    except database.DatabaseConfigurationError as exc:
        raise RuntimeError(str(exc)) from exc


def run_migrations_offline() -> None:
    context.configure(
        url=get_migration_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        get_migration_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
