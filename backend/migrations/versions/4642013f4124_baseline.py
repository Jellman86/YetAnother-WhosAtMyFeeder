"""Baseline schema

Revision ID: 4642013f4124
Revises: 
Create Date: 2026-01-03 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4642013f4124'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Use batch_alter_table for SQLite compatibility
    op.create_table(
        'detections',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('detection_time', sa.DateTime(), nullable=False),
        sa.Column('detection_index', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('category_name', sa.String(), nullable=False),
        sa.Column('frigate_event', sa.String(), nullable=False, unique=True),
        sa.Column('camera_name', sa.String(), nullable=False),
        sa.Column('is_hidden', sa.Boolean(), server_default='0'),
        sa.Column('frigate_score', sa.Float()),
        sa.Column('sub_label', sa.String()),
        sa.Column('audio_confirmed', sa.Boolean(), server_default='0'),
        sa.Column('audio_species', sa.String()),
        sa.Column('audio_score', sa.Float()),
        sa.Column('temperature', sa.Float()),
        sa.Column('weather_condition', sa.String())
    )
    op.create_index('idx_detections_time', 'detections', ['detection_time'])
    op.create_index('idx_detections_species', 'detections', ['display_name'])
    op.create_index('idx_detections_hidden', 'detections', ['is_hidden'])
    op.create_index('idx_detections_camera', 'detections', ['camera_name'])

def downgrade() -> None:
    op.drop_index('idx_detections_camera')
    op.drop_index('idx_detections_hidden')
    op.drop_index('idx_detections_species')
    op.drop_index('idx_detections_time')
    op.drop_table('detections')
