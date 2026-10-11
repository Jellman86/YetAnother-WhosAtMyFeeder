"""Retain verified Frigate event bounds for visit grouping.

Revision ID: a6f491c8de20
Revises: c7d4e2a9f150
"""

from alembic import op
import sqlalchemy as sa

revision = "a6f491c8de20"
down_revision = "c7d4e2a9f150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("snapshot_candidate_dismissals"):
        op.create_table(
            "snapshot_candidate_dismissals",
            sa.Column(
                "frigate_event",
                sa.String(),
                sa.ForeignKey("detections.frigate_event", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("candidate_id", sa.String(), primary_key=True),
            sa.Column("content_identity", sa.String(), nullable=False),
        )
    if not sa.inspect(op.get_bind()).has_table("detection_event_bounds"):
        op.create_table(
            "detection_event_bounds",
            sa.Column(
                "frigate_event",
                sa.String(),
                sa.ForeignKey("detections.frigate_event", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("start_time", sa.DateTime(), nullable=False),
            sa.Column("end_time", sa.DateTime(), nullable=False),
            sa.CheckConstraint("end_time >= start_time", name="ck_detection_event_bounds_order"),
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("snapshot_candidate_dismissals"):
        op.drop_table("snapshot_candidate_dismissals")
    if sa.inspect(op.get_bind()).has_table("detection_event_bounds"):
        op.drop_table("detection_event_bounds")
