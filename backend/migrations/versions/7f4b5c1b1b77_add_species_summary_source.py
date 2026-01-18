"""Add summary source fields to species info cache

Revision ID: 7f4b5c1b1b77
Revises: 6f6b0fe33d3a
Create Date: 2026-01-18 13:36:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f4b5c1b1b77'
down_revision: Union[str, None] = '6f6b0fe33d3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'species_info_cache' in tables:
        with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
            batch_op.add_column(sa.Column('summary_source', sa.String(), nullable=True))
            batch_op.add_column(sa.Column('summary_source_url', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('species_info_cache', schema=None) as batch_op:
        batch_op.drop_column('summary_source_url')
        batch_op.drop_column('summary_source')
