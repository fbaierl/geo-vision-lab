"""Alembic environment configuration for GeoVision Lab migrations."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment if set
db_url = os.getenv(
    "POSTGRES_URI",
    config.get_main_option("sqlalchemy.url"),
)
config.set_main_option("sqlalchemy.url", db_url)

# Set up Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No SQLAlchemy MetaData object for autogenerate — we use raw SQL migrations
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
