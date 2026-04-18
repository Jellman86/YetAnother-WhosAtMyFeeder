"""Add snapshot_candidates table.

Revision ID: 9c1b2a3d4e5f
Revises: e2f3a4b5c6d7
Create Date: 2026-04-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '9c1b2a3d4e5f'
down_revision = 'a7e2f8b3c9d1'
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
    if not _has_table(bind, "snapshot_candidates"):
        op.create_table(
            "snapshot_candidates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("frigate_event", sa.String(), nullable=False),
            sa.Column("candidate_id", sa.String(), nullable=False),
            sa.Column("frame_index", sa.Integer(), nullable=False),
            sa.Column("frame_offset_seconds", sa.Float(), nullable=True),
            sa.Column("source_mode", sa.String(), nullable=False),
            sa.Column("clip_variant", sa.String(), nullable=False),
            sa.Column("crop_box_json", sa.Text(), nullable=True),
            sa.Column("crop_confidence", sa.Float(), nullable=True),
            sa.Column("classifier_label", sa.String(), nullable=True),
            sa.Column("classifier_score", sa.Float(), nullable=True),
            sa.Column("ranking_score", sa.Float(), nullable=False),
            sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("thumbnail_ref", sa.String(), nullable=True),
            sa.Column("image_ref", sa.String(), nullable=True),
            sa.Column("snapshot_source", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("frigate_event", "candidate_id", name="uq_snapshot_candidates_event_candidate"),
        )

    if not _has_index(bind, "snapshot_candidates", "ix_snapshot_candidates_event"):
        op.create_index("ix_snapshot_candidates_event", "snapshot_candidates", ["frigate_event"])
    if not _has_index(bind, "snapshot_candidates", "ix_snapshot_candidates_event_selected"):
        op.create_index("ix_snapshot_candidates_event_selected", "snapshot_candidates", ["frigate_event", "selected"])


def downgrade():
    bind = op.get_bind()
    if not _has_table(bind, "snapshot_candidates"):
        return
    if _has_index(bind, "snapshot_candidates", "ix_snapshot_candidates_event_selected"):
        op.drop_index("ix_snapshot_candidates_event_selected", table_name="snapshot_candidates")
    if _has_index(bind, "snapshot_candidates", "ix_snapshot_candidates_event"):
        op.drop_index("ix_snapshot_candidates_event", table_name="snapshot_candidates")
    op.drop_table("snapshot_candidates")
