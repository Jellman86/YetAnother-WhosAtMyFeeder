"""Add taxa_id to species info cache

Revision ID: 6f6b0fe33d3a
Revises: 3c3b5f7f2c7a
Create Date: 2026-01-18 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f6b0fe33d3a'
down_revision: Union[str, None] = '3c3b5f7f2c7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _index_names(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA index_list({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'species_info_cache' in tables:
        cols = _get_columns(bind, "species_info_cache")
        indexes = _index_names(bind, "species_info_cache")
        with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
            if "taxa_id" not in cols:
                batch_op.add_column(sa.Column('taxa_id', sa.Integer(), nullable=True))
            if "idx_species_info_taxa_id" not in indexes:
                batch_op.create_index('idx_species_info_taxa_id', ['taxa_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if 'species_info_cache' not in tables:
        return

    cols = _get_columns(bind, "species_info_cache")
    indexes = _index_names(bind, "species_info_cache")
    with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
        if "idx_species_info_taxa_id" in indexes:
            batch_op.drop_index('idx_species_info_taxa_id')
        if "taxa_id" in cols:
            batch_op.drop_column('taxa_id')
