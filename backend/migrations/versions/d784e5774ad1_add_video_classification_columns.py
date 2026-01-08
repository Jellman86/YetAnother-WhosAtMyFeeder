"""add_video_classification_columns

Revision ID: d784e5774ad1
Revises: 568e70ba4be2
Create Date: 2026-01-08 19:10:49.866051

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd784e5774ad1'
down_revision: Union[str, None] = '568e70ba4be2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('detections', sa.Column('video_classification_score', sa.Float(), nullable=True))
    op.add_column('detections', sa.Column('video_classification_label', sa.String(), nullable=True))
    op.add_column('detections', sa.Column('video_classification_index', sa.Integer(), nullable=True))
    op.add_column('detections', sa.Column('video_classification_timestamp', sa.TIMESTAMP(), nullable=True))
    op.add_column('detections', sa.Column('video_classification_status', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('detections', 'video_classification_status')
    op.drop_column('detections', 'video_classification_timestamp')
    op.drop_column('detections', 'video_classification_index')
    op.drop_column('detections', 'video_classification_label')
    op.drop_column('detections', 'video_classification_score')