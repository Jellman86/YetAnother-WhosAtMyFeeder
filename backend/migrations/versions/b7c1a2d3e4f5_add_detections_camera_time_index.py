"""Add composite index on detections(camera_name, detection_time).

Revision ID: b7c1a2d3e4f5
Revises: e2f3a4b5c6d7
Create Date: 2026-02-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b7c1a2d3e4f5"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("PRAGMA index_list(detections)")).fetchall()
    existing = {row[1] for row in rows}
    if "idx_detections_camera_time" not in existing:
        op.create_index(
            "idx_detections_camera_time",
            "detections",
            ["camera_name", "detection_time"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("PRAGMA index_list(detections)")).fetchall()
    existing = {row[1] for row in rows}
    if "idx_detections_camera_time" in existing:
        op.drop_index("idx_detections_camera_time", table_name="detections")
