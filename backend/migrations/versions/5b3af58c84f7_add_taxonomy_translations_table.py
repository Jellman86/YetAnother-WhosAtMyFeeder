"""add_taxonomy_translations_table

Revision ID: 5b3af58c84f7
Revises: 82070193ce11
Create Date: 2026-01-13 09:24:11.253020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b3af58c84f7'
down_revision: Union[str, None] = '82070193ce11'
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


def upgrade() -> None:
    conn = op.get_bind()
    # taxonomy_cache is created in the initial migration; if it's missing, we can't
    # safely add a FK-constrained translations table.
    if not _table_exists(conn, "taxonomy_cache"):
        return

    if not _table_exists(conn, "taxonomy_translations"):
        op.create_table(
            'taxonomy_translations',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('taxa_id', sa.Integer(), nullable=False),
            sa.Column('language_code', sa.String(5), nullable=False),
            sa.Column('common_name', sa.String(), nullable=False),
            sa.ForeignKeyConstraint(['taxa_id'], ['taxonomy_cache.taxa_id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('taxa_id', 'language_code', name='uq_taxa_lang')
        )

    if not _index_exists(conn, "idx_taxonomy_trans_taxa"):
        op.create_index('idx_taxonomy_trans_taxa', 'taxonomy_translations', ['taxa_id'])
    if not _index_exists(conn, "idx_taxonomy_trans_lang"):
        op.create_index('idx_taxonomy_trans_lang', 'taxonomy_translations', ['language_code'])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_taxonomy_trans_lang")
    op.execute("DROP INDEX IF EXISTS idx_taxonomy_trans_taxa")
    op.execute("DROP TABLE IF EXISTS taxonomy_translations")
