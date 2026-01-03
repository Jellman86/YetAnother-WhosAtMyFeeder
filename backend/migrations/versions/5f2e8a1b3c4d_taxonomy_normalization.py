"""Add taxonomy normalization

Revision ID: 5f2e8a1b3c4d
Revises: 4642013f4124
Create Date: 2026-01-03 12:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5f2e8a1b3c4d'
down_revision: Union[str, None] = '4642013f4124'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Create taxonomy_cache table
    op.create_table(
        'taxonomy_cache',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('scientific_name', sa.String(), nullable=False, unique=True),
        sa.Column('common_name', sa.String()),
        sa.Column('taxa_id', sa.Integer()),
        sa.Column('is_not_found', sa.Boolean(), server_default='0'),
        sa.Column('last_updated', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('idx_taxonomy_scientific', 'taxonomy_cache', ['scientific_name'])
    op.create_index('idx_taxonomy_common', 'taxonomy_cache', ['common_name'])

    # 2. Add columns to detections table
    # Using batch_alter_table for SQLite compatibility
    with op.batch_alter_table('detections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scientific_name', sa.String()))
        batch_op.add_column(sa.Column('common_name', sa.String()))
        batch_op.add_column(sa.Column('taxa_id', sa.Integer()))
        batch_op.create_index('idx_detections_scientific', ['scientific_name'])
        batch_op.create_index('idx_detections_common', ['common_name'])
        batch_op.create_index('idx_detections_taxa_id', ['taxa_id'])

def downgrade() -> None:
    with op.batch_alter_table('detections', schema=None) as batch_op:
        batch_op.drop_index('idx_detections_taxa_id')
        batch_op.drop_index('idx_detections_common')
        batch_op.drop_index('idx_detections_scientific')
        batch_op.drop_column('taxa_id')
        batch_op.drop_column('common_name')
        batch_op.drop_column('scientific_name')

    op.drop_index('idx_taxonomy_common')
    op.drop_index('idx_taxonomy_scientific')
    op.drop_table('taxonomy_cache')
