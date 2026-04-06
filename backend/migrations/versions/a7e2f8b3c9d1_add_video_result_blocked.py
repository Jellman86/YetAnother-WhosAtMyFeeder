"""add video_result_blocked to detections

Track whether a completed video classification result was suppressed because
the top species matched a blocked entry.  The column is set to 1 when the
backend stores a video result but deliberately does not promote it to the
primary detection species.  The UI surfaces this as an amber "blocked label"
note in the detection modal.

Revision ID: a7e2f8b3c9d1
Revises: f1a2b3c4d5e6
Create Date: 2026-04-06

Risk: Low — additive schema only, nullable column with safe default.
Downgrade: fully reversible (column drop, data loss of blocked flag only).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'a7e2f8b3c9d1'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table: str, column: str) -> bool:
    inspector = inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "detections", "video_result_blocked"):
        # Guard: idempotent — column already present (e.g. partial prior run)
        return
    with op.batch_alter_table("detections") as batch_op:
        batch_op.add_column(
            sa.Column(
                "video_result_blocked",
                sa.Boolean(),
                nullable=True,
                server_default="0",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "detections", "video_result_blocked"):
        # Guard: idempotent — column already absent
        return
    with op.batch_alter_table("detections") as batch_op:
        batch_op.drop_column("video_result_blocked")
