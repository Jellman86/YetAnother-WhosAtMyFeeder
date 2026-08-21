"""Alembic environment for the species catalogue database.

A separate stream from the main `speciesid.db` environment on purpose: the
catalogue can be enriched, validated, and rolled back without holding a
migration lock over detection history, and neither stream can ever depend on
the other's revisions.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.append(os.getcwd())

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The catalogue schema is defined in its migrations, not in model metadata.
target_metadata = None


def get_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    db_path = os.environ.get("SPECIES_CATALOG_PATH", "/data/species_catalog.db")
    return f"sqlite:///{db_path}"


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
