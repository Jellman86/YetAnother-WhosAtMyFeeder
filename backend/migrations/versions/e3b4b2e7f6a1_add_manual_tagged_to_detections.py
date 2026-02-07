"""Add manual_tagged to detections.

Revision ID: e3b4b2e7f6a1
Revises: d784e5774ad1
Create Date: 2026-01-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e3b4b2e7f6a1"
down_revision = "d784e5774ad1"
branch_labels = None
depends_on = None


def _get_columns(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    if "manual_tagged" not in cols:
        op.add_column(
            "detections",
            sa.Column("manual_tagged", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    cols = _get_columns(conn, "detections")
    with op.batch_alter_table("detections", schema=None) as batch_op:
        if "manual_tagged" in cols:
            batch_op.drop_column("manual_tagged")
