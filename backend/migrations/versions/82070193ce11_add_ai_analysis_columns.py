"""add_ai_analysis_columns

Revision ID: 82070193ce11
Revises: d784e5774ad1
Create Date: 2026-01-13 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82070193ce11'
down_revision: Union[str, None] = 'd784e5774ad1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('detections', sa.Column('ai_analysis', sa.String(), nullable=True))
    op.add_column('detections', sa.Column('ai_analysis_timestamp', sa.TIMESTAMP(), nullable=True))


def downgrade() -> None:
    op.drop_column('detections', 'ai_analysis_timestamp')
    op.drop_column('detections', 'ai_analysis')
