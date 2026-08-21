"""Programmatic access to the species catalogue's migration stream.

The catalogue database has its own single-head Alembic environment
(`alembic_catalog.ini` / `migrations_catalog/`), deliberately separate from the
main `speciesid.db` stream: taxonomy can be migrated, enriched, and rolled back
without holding any lock over detection history, and neither stream can depend
on the other's revisions.

These helpers are synchronous because Alembic is; callers on the event loop
dispatch them through a worker thread.
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_DIR = Path(__file__).resolve().parents[2]
CATALOG_INI = _BACKEND_DIR / "alembic_catalog.ini"


def default_catalog_path() -> Path:
    configured = os.environ.get("SPECIES_CATALOG_PATH")
    if configured:
        return Path(configured)
    return Path("/data/species_catalog.db")


def catalog_alembic_config(db_path: Path | None = None) -> Config:
    config = Config(str(CATALOG_INI))
    config.set_main_option("script_location", str(_BACKEND_DIR / "migrations_catalog"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path or default_catalog_path()}")
    return config


def catalog_migration_heads() -> list[str]:
    script = ScriptDirectory.from_config(catalog_alembic_config(Path(":memory:")))
    return list(script.get_heads())


def upgrade_catalog(db_path: Path | None = None, revision: str = "head") -> None:
    command.upgrade(catalog_alembic_config(db_path), revision)


def downgrade_catalog(db_path: Path | None = None, revision: str = "-1") -> None:
    command.downgrade(catalog_alembic_config(db_path), revision)
