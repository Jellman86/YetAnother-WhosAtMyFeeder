"""Record what a favourite's archive holds (#178).

A favourite used to be a marker: it kept the detection row and whatever the media cache
happened to hold out of retention cleanup, and said nothing about whether the photograph or
clip would survive a cache clear or Frigate's own rotation. These columns carry the archive's
state per asset so the star can say what is actually durable, what Frigate no longer had, and
what failed and will be retried.

Existing favourites start as pending/pending; the archive worker's reconcile pass acquires
them without anyone pressing anything.

Revision ID: b8e1f2a3c4d5
Revises: a7c4e2f9d1b3
Create Date: 2026-09-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e1f2a3c4d5"
down_revision: Union[str, None] = "a7c4e2f9d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "detection_favorites"
COLUMN_NAMES = (
    "archive_snapshot_state",
    "archive_clip_state",
    "archive_bytes",
    "archive_attempts",
    "archive_error",
    "archived_at",
    "archive_updated_at",
)


def _columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("archive_snapshot_state", sa.String(), nullable=False, server_default="pending"),
        sa.Column("archive_clip_state", sa.String(), nullable=False, server_default="pending"),
        sa.Column("archive_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archive_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archive_error", sa.String(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("archive_updated_at", sa.DateTime(), nullable=True),
    )


def _existing_columns(bind: sa.engine.Connection) -> set[str]:
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return set()
    return {str(column.get("name")) for column in inspector.get_columns(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind)
    for column in _columns():
        if column.name not in existing:
            op.add_column(TABLE, column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind)
    to_drop = [name for name in COLUMN_NAMES if name in existing]
    if not to_drop:
        return
    with op.batch_alter_table(TABLE) as batch_op:
        for name in to_drop:
            batch_op.drop_column(name)
