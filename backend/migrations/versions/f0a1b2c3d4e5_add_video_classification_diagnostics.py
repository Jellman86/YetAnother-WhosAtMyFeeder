"""Persist bounded video classification evidence.

Revision ID: f0a1b2c3d4e5
Revises: e9a2b3c4d5f6
Create Date: 2026-08-01 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9a2b3c4d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(detections)")).fetchall()
    return {str(row[1]) for row in rows}


def upgrade() -> None:
    if "video_classification_diagnostics" not in _columns():
        op.add_column(
            "detections",
            sa.Column("video_classification_diagnostics", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if "video_classification_diagnostics" in _columns():
        with op.batch_alter_table("detections", schema=None) as batch_op:
            batch_op.drop_column("video_classification_diagnostics")
