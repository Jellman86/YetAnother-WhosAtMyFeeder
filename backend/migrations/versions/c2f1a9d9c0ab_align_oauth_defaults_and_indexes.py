"""align oauth defaults and missing indexes

Revision ID: c2f1a9d9c0ab
Revises: 9b8f1d0c2a7b
Create Date: 2026-01-17 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2f1a9d9c0ab'
down_revision: Union[str, None] = '9b8f1d0c2a7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Ensure detections video status index exists
    if 'detections' in inspector.get_table_names():
        index_names = {idx['name'] for idx in inspector.get_indexes('detections')}
        if 'idx_detections_video_status' not in index_names:
            op.create_index('idx_detections_video_status', 'detections', ['video_classification_status'])

    # Add server defaults to oauth token timestamps if missing
    if 'oauth_tokens' in inspector.get_table_names():
        with op.batch_alter_table('oauth_tokens', schema=None) as batch_op:
            batch_op.alter_column(
                'created_at',
                existing_type=sa.DateTime(),
                server_default=sa.text('(CURRENT_TIMESTAMP)'),
                existing_nullable=False
            )
            batch_op.alter_column(
                'updated_at',
                existing_type=sa.DateTime(),
                server_default=sa.text('(CURRENT_TIMESTAMP)'),
                existing_nullable=False
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'detections' in inspector.get_table_names():
        index_names = {idx['name'] for idx in inspector.get_indexes('detections')}
        if 'idx_detections_video_status' in index_names:
            op.drop_index('idx_detections_video_status', table_name='detections')

    if 'oauth_tokens' in inspector.get_table_names():
        with op.batch_alter_table('oauth_tokens', schema=None) as batch_op:
            batch_op.alter_column(
                'created_at',
                existing_type=sa.DateTime(),
                server_default=None,
                existing_nullable=False
            )
            batch_op.alter_column(
                'updated_at',
                existing_type=sa.DateTime(),
                server_default=None,
                existing_nullable=False
            )
