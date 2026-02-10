"""Fix taxonomy_translations foreign key for SQLite upgrades.

On some upgraded installations, taxonomy_translations was created with an FK to
taxonomy_cache.taxa_id. In SQLite, FK parent keys must be PRIMARY KEY or UNIQUE,
and taxonomy_cache.taxa_id is not guaranteed to be unique/stable. This can yield:

  sqlite3.OperationalError: foreign key mismatch - "taxonomy_translations" referencing "taxonomy_cache"

This migration rebuilds taxonomy_translations without the FK constraint (cache-only table).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3d9c1e7b5f2"
down_revision: Union[str, None] = "c9d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def _index_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def _has_foreign_keys(conn, table: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA foreign_key_list({table})")).fetchall()
    return bool(rows)


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "taxonomy_translations"):
        return

    # If there is no FK, nothing to do (keep data + indices stable).
    if not _has_foreign_keys(conn, "taxonomy_translations"):
        return

    # Rebuild without FK. Use PRAGMA foreign_keys=OFF to avoid mismatch errors mid-migration.
    op.execute("PRAGMA foreign_keys=OFF")
    try:
        # Create replacement table.
        op.create_table(
            "taxonomy_translations_new",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("taxa_id", sa.Integer(), nullable=False),
            sa.Column("language_code", sa.String(5), nullable=False),
            sa.Column("common_name", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("taxa_id", "language_code", name="uq_taxa_lang"),
        )

        # Copy data.
        op.execute(
            """
            INSERT INTO taxonomy_translations_new (id, taxa_id, language_code, common_name)
            SELECT id, taxa_id, language_code, common_name
            FROM taxonomy_translations
            """
        )

        # Replace old table.
        op.execute("DROP TABLE taxonomy_translations")
        op.execute("ALTER TABLE taxonomy_translations_new RENAME TO taxonomy_translations")

        # Recreate indices (idempotent).
        if not _index_exists(conn, "idx_taxonomy_trans_taxa"):
            op.create_index("idx_taxonomy_trans_taxa", "taxonomy_translations", ["taxa_id"])
        if not _index_exists(conn, "idx_taxonomy_trans_lang"):
            op.create_index("idx_taxonomy_trans_lang", "taxonomy_translations", ["language_code"])
    finally:
        op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    # Downgrade is intentionally a no-op:
    # restoring the FK would reintroduce the upgrade failure mode on SQLite.
    pass

