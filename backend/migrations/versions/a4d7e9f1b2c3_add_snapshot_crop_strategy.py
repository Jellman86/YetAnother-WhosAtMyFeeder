"""Add crop strategy provenance to snapshot candidates.

Revision ID: a4d7e9f1b2c3
Revises: f8b2c4d6e9a1
Create Date: 2026-07-21 16:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4d7e9f1b2c3"
down_revision: Union[str, None] = "f8b2c4d6e9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind: sa.engine.Connection, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "snapshot_candidates", "crop_strategy"):
        op.add_column("snapshot_candidates", sa.Column("crop_strategy", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "snapshot_candidates", "crop_strategy"):
        with op.batch_alter_table("snapshot_candidates") as batch_op:
            batch_op.drop_column("crop_strategy")
