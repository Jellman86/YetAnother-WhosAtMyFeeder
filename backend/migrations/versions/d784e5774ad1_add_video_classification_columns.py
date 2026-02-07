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


def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    if "video_classification_score" not in cols:
        op.add_column('detections', sa.Column('video_classification_score', sa.Float(), nullable=True))
    if "video_classification_label" not in cols:
        op.add_column('detections', sa.Column('video_classification_label', sa.String(), nullable=True))
    if "video_classification_index" not in cols:
        op.add_column('detections', sa.Column('video_classification_index', sa.Integer(), nullable=True))
    if "video_classification_timestamp" not in cols:
        op.add_column('detections', sa.Column('video_classification_timestamp', sa.TIMESTAMP(), nullable=True))
    if "video_classification_status" not in cols:
        op.add_column('detections', sa.Column('video_classification_status', sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    with op.batch_alter_table("detections", schema=None) as batch_op:
        if "video_classification_status" in cols:
            batch_op.drop_column('video_classification_status')
        if "video_classification_timestamp" in cols:
            batch_op.drop_column('video_classification_timestamp')
        if "video_classification_index" in cols:
            batch_op.drop_column('video_classification_index')
        if "video_classification_label" in cols:
            batch_op.drop_column('video_classification_label')
        if "video_classification_score" in cols:
            batch_op.drop_column('video_classification_score')
