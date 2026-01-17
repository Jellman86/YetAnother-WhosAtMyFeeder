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


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'species_info_cache' not in tables:
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
        with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
            batch_op.create_index('idx_species_info_name', ['species_name'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
        batch_op.drop_index('idx_species_info_name')
    op.drop_table('species_info_cache')
