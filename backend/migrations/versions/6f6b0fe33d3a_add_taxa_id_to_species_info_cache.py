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


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'species_info_cache' in tables:
        with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
            batch_op.add_column(sa.Column('taxa_id', sa.Integer(), nullable=True))
            batch_op.create_index('idx_species_info_taxa_id', ['taxa_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
        batch_op.drop_index('idx_species_info_taxa_id')
        batch_op.drop_column('taxa_id')
