"""Add durable manual-observation analysis drafts.

Revision ID: d8f1a2b3c4e5
Revises: c7e4a9b2d1f6
Create Date: 2026-08-01 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "d8f1a2b3c4e5"
down_revision: Union[str, None] = "c7e4a9b2d1f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "manual_observation_drafts"):
        return
    op.create_table(
        "manual_observation_drafts",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("source_filename", sa.String(length=80), nullable=False),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_message", sa.String(length=255), nullable=True),
        sa.Column("results_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("saved_event_id", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("content_sha256", name="uq_manual_observation_drafts_sha256"),
        sa.UniqueConstraint("saved_event_id", name="uq_manual_observation_drafts_event_id"),
    )
    op.create_index("ix_manual_observation_drafts_status", "manual_observation_drafts", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "manual_observation_drafts"):
        op.drop_table("manual_observation_drafts")
