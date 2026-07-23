"""Add stable BirdNET source identity for idempotent audio ingest.

Revision ID: c7e4a9b2d1f6
Revises: a4d7e9f1b2c3
Create Date: 2026-07-22 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "c7e4a9b2d1f6"
down_revision: Union[str, None] = "a4d7e9f1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return any(column.get("name") == column_name for column in inspect(bind).get_columns(table_name))


def _has_index(bind, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "audio_detections", "source_event_id"):
        with op.batch_alter_table("audio_detections") as batch_op:
            batch_op.add_column(sa.Column("source_event_id", sa.String(length=512), nullable=True))
    if not _has_index(bind, "audio_detections", "uq_audio_detections_source_event_id"):
        op.create_index(
            "uq_audio_detections_source_event_id",
            "audio_detections",
            ["source_event_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, "audio_detections", "uq_audio_detections_source_event_id"):
        op.drop_index("uq_audio_detections_source_event_id", table_name="audio_detections")
    if _has_column(bind, "audio_detections", "source_event_id"):
        with op.batch_alter_table("audio_detections") as batch_op:
            batch_op.drop_column("source_event_id")
