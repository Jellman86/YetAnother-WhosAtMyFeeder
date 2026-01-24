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


def upgrade() -> None:
    op.add_column(
        "detections",
        sa.Column("notified_at", sa.TIMESTAMP(), nullable=True),
    )
    with op.batch_alter_table("detections", schema=None) as batch_op:
        batch_op.create_index("idx_detections_notified_at", ["notified_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("detections", schema=None) as batch_op:
        batch_op.drop_index("idx_detections_notified_at")
    op.drop_column("detections", "notified_at")
