"""Retain bounded private motion evidence without fabricated Frigate events.

Revision ID: a21e40b5c610
Revises: f912a3d4e510
"""

from alembic import op
import sqlalchemy as sa

revision = "a21e40b5c610"
down_revision = "f912a3d4e510"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "garden_motion_sources" not in tables:
        op.create_table(
            "garden_motion_sources",
            sa.Column("capture_id", sa.String(32), primary_key=True),
            sa.Column("source_json", sa.Text(), nullable=False),
            sa.Column("image", sa.LargeBinary(), nullable=True),
            sa.Column("expires_at", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(["capture_id"], ["garden_captures.id"], ondelete="CASCADE"),
            sa.CheckConstraint("json_valid(source_json)", name="ck_garden_motion_source_json"),
            sa.CheckConstraint("image IS NULL OR length(image) <= 524288", name="ck_garden_motion_photo_size"),
        )
    op.execute("""CREATE INDEX IF NOT EXISTS ix_garden_motion_camera_end ON garden_motion_sources
               (json_extract(source_json,'$.camera'), json_extract(source_json,'$.clip_end'))""")
    if "garden_motion_cursors" not in tables:
        op.create_table(
            "garden_motion_cursors",
            sa.Column("camera", sa.String(100), primary_key=True),
            sa.Column("last_end", sa.Float(), nullable=False),
            sa.CheckConstraint("last_end > 0", name="ck_garden_motion_cursor_positive"),
        )


def downgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "garden_motion_sources" in tables:
        # Rollback discards replaceable photos/provenance, never confirmed history.
        op.execute(
            "UPDATE garden_captures SET has_snapshot=0 WHERE id IN (SELECT capture_id FROM garden_motion_sources)"
        )
        op.drop_table("garden_motion_sources")
    if "garden_motion_cursors" in tables:
        op.drop_table("garden_motion_cursors")
