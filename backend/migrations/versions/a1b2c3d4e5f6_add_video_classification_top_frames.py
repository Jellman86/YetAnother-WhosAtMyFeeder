"""Add video_classification_top_frames table.

Revision ID: a1b2c3d4e5f6
Revises: 9c1b2a3d4e5f
Create Date: 2026-04-18 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9c1b2a3d4e5f'
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_index(bind, table_name: str, index_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    indexes = inspect(bind).get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def upgrade():
    bind = op.get_bind()
    if not _has_table(bind, "video_classification_top_frames"):
        op.create_table(
            "video_classification_top_frames",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("frigate_event", sa.String(), nullable=False),
            sa.Column("clip_variant", sa.String(), nullable=False),
            sa.Column("frame_index", sa.Integer(), nullable=False),
            sa.Column("frame_offset_seconds", sa.Float(), nullable=True),
            sa.Column("frame_score", sa.Float(), nullable=False),
            sa.Column("top_label", sa.String(), nullable=True),
            sa.Column("top_score", sa.Float(), nullable=True),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not _has_index(bind, "video_classification_top_frames", "ix_video_top_frames_event_rank"):
        op.create_index(
            "ix_video_top_frames_event_rank",
            "video_classification_top_frames",
            ["frigate_event", "rank"],
        )
    if not _has_index(bind, "video_classification_top_frames", "ix_video_top_frames_event_created"):
        op.create_index(
            "ix_video_top_frames_event_created",
            "video_classification_top_frames",
            ["frigate_event", "created_at"],
        )


def downgrade():
    bind = op.get_bind()
    if not _has_table(bind, "video_classification_top_frames"):
        return
    if _has_index(bind, "video_classification_top_frames", "ix_video_top_frames_event_created"):
        op.drop_index("ix_video_top_frames_event_created", table_name="video_classification_top_frames")
    if _has_index(bind, "video_classification_top_frames", "ix_video_top_frames_event_rank"):
        op.drop_index("ix_video_top_frames_event_rank", table_name="video_classification_top_frames")
    op.drop_table("video_classification_top_frames")
