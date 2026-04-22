"""Add Frigate missing-state tracking to detections.

Revision ID: b5e6f7a8c9d0
Revises: a1b2c3d4e5f6
Create Date: 2026-04-22 20:10:00.000000

This tracks whether a detection is still backed by an upstream Frigate event
or retained media. YA-WAMF may intentionally retain local detections longer
than Frigate, so the status must be observable and policy-driven instead of
implicitly deleting rows.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "b5e6f7a8c9d0"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    return any(col["name"] == column_name for col in inspect(bind).get_columns(table_name))


def _has_index(bind, table_name: str, index_name: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    return any(index.get("name") == index_name for index in inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("detections", schema=None) as batch_op:
        if not _has_column(bind, "detections", "frigate_status"):
            batch_op.add_column(
                sa.Column(
                    "frigate_status",
                    sa.String(),
                    nullable=True,
                    server_default="present",
                )
            )
        if not _has_column(bind, "detections", "frigate_missing_since"):
            batch_op.add_column(sa.Column("frigate_missing_since", sa.TIMESTAMP(), nullable=True))
        if not _has_column(bind, "detections", "frigate_last_checked_at"):
            batch_op.add_column(sa.Column("frigate_last_checked_at", sa.TIMESTAMP(), nullable=True))
        if not _has_column(bind, "detections", "frigate_last_error"):
            batch_op.add_column(sa.Column("frigate_last_error", sa.String(), nullable=True))

    if not _has_index(bind, "detections", "idx_detections_frigate_status"):
        op.create_index(
            "idx_detections_frigate_status",
            "detections",
            ["frigate_status"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, "detections", "idx_detections_frigate_status"):
        op.drop_index("idx_detections_frigate_status", table_name="detections")

    with op.batch_alter_table("detections", schema=None) as batch_op:
        if _has_column(bind, "detections", "frigate_last_error"):
            batch_op.drop_column("frigate_last_error")
        if _has_column(bind, "detections", "frigate_last_checked_at"):
            batch_op.drop_column("frigate_last_checked_at")
        if _has_column(bind, "detections", "frigate_missing_since"):
            batch_op.drop_column("frigate_missing_since")
        if _has_column(bind, "detections", "frigate_status"):
            batch_op.drop_column("frigate_status")
