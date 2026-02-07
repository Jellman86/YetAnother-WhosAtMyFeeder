"""Add notified_at to detections.

Revision ID: b1c2d3e4f5a6
Revises: 0f2a3b6c9d11
Create Date: 2026-01-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "0f2a3b6c9d11"
branch_labels = None
depends_on = None


def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _get_indexes(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA index_list({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    if "notified_at" not in cols:
        op.add_column(
            "detections",
            sa.Column("notified_at", sa.TIMESTAMP(), nullable=True),
        )

    indexes = _get_indexes(conn, "detections")
    if "idx_detections_notified_at" not in indexes:
        with op.batch_alter_table("detections", schema=None) as batch_op:
            batch_op.create_index("idx_detections_notified_at", ["notified_at"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    indexes = _get_indexes(conn, "detections")
    if "idx_detections_notified_at" in indexes:
        with op.batch_alter_table("detections", schema=None) as batch_op:
            batch_op.drop_index("idx_detections_notified_at")

    cols = _get_columns(conn, "detections")
    with op.batch_alter_table("detections", schema=None) as batch_op:
        if "notified_at" in cols:
            batch_op.drop_column("notified_at")
