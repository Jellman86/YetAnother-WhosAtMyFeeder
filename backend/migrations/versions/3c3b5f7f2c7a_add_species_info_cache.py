"""Add species info cache table

Revision ID: 3c3b5f7f2c7a
Revises: 10b7668f28ac
Create Date: 2026-01-18 10:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c3b5f7f2c7a'
down_revision: Union[str, None] = '10b7668f28ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "species_info_cache"):
        op.create_table(
            'species_info_cache',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('species_name', sa.String(), nullable=False),
            sa.Column('title', sa.String(), nullable=True),
            sa.Column('source', sa.String(), nullable=True),
            sa.Column('source_url', sa.String(), nullable=True),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('extract', sa.String(), nullable=True),
            sa.Column('thumbnail_url', sa.String(), nullable=True),
            sa.Column('wikipedia_url', sa.String(), nullable=True),
            sa.Column('scientific_name', sa.String(), nullable=True),
            sa.Column('conservation_status', sa.String(), nullable=True),
            sa.Column('cached_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('species_name')
        )
    if _table_exists(bind, "species_info_cache") and not _index_exists(bind, "species_info_cache", "idx_species_info_name"):
        with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
            batch_op.create_index('idx_species_info_name', ['species_name'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "species_info_cache"):
        return
    if _index_exists(bind, "species_info_cache", "idx_species_info_name"):
        with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
            batch_op.drop_index('idx_species_info_name')
    op.drop_table('species_info_cache')
