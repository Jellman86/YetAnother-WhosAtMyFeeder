"""Add persistent state for bounded background processing retries.

Revision ID: d6e7f8a9b0c1
Revises: b5e6f7a8c9d0
Create Date: 2026-07-20 11:00:00.000000

The table is intentionally independent from detections: retry bookkeeping
must never mutate or constrain canonical species identity. Rows are small and
event-scoped, with a lookup index supporting reconciliation workers.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "b5e6f7a8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_index(bind, table_name: str, index_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    return any(index.get("name") == index_name for index in inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "processing_job_state"):
        op.create_table(
            "processing_job_state",
            sa.Column("pipeline", sa.String(length=64), nullable=False),
            sa.Column(
                "event_id",
                sa.String(length=255),
                sa.ForeignKey("detections.frigate_event", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("retry_after", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.String(length=500), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("pipeline", "event_id", name="pk_processing_job_state"),
        )
    if not _has_index(bind, "processing_job_state", "ix_processing_job_state_status_retry"):
        op.create_index(
            "ix_processing_job_state_status_retry",
            "processing_job_state",
            ["pipeline", "status", "retry_after"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "processing_job_state"):
        return
    if _has_index(bind, "processing_job_state", "ix_processing_job_state_status_retry"):
        op.drop_index("ix_processing_job_state_status_retry", table_name="processing_job_state")
    op.drop_table("processing_job_state")
