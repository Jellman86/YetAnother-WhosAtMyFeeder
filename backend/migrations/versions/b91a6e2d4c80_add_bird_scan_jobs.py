"""Persist immutable-scene bird scan requests and revision-fenced outcomes.

Revision ID: b91a6e2d4c80
Revises: a6f491c8de20
"""

from alembic import op
import sqlalchemy as sa

revision = "b91a6e2d4c80"
down_revision = "a6f491c8de20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("bird_scan_jobs"):
        op.create_table(
            "bird_scan_jobs",
            sa.Column(
                "frigate_event",
                sa.String(),
                sa.ForeignKey("detections.frigate_event", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("generation", sa.String(32), nullable=False),
            sa.Column("candidate_id", sa.String(), nullable=False),
            sa.Column("image_ref", sa.String(), nullable=False),
            sa.Column("content_sha256", sa.String(64), nullable=False),
            sa.Column("media_version", sa.String(), nullable=False),
            sa.Column("clip_variant", sa.String(), nullable=False),
            sa.Column("frame_index", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("result_count", sa.Integer()),
            sa.Column("retained_previous", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("error", sa.String()),
            sa.CheckConstraint("status IN ('queued','running','completed','failed')", name="ck_bird_scan_jobs_status"),
            sa.CheckConstraint("revision >= 1", name="ck_bird_scan_jobs_revision"),
            sa.CheckConstraint("result_count IS NULL OR result_count >= 0", name="ck_bird_scan_jobs_count"),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("bird_scan_jobs")}
    if "ix_bird_scan_jobs_status_created" not in indexes:
        op.create_index("ix_bird_scan_jobs_status_created", "bird_scan_jobs", ["status", "created_at", "frigate_event"])


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("bird_scan_jobs"):
        op.drop_table("bird_scan_jobs")
