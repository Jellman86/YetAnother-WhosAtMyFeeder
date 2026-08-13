"""Add a durable manual common-name override.

Revision ID: c7d8e9f0a1b2
Revises: f0a1b2c3d4e5
Create Date: 2026-08-08 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(taxonomy_cache)")).fetchall()
    return {str(row[1]) for row in rows}


def upgrade() -> None:
    if "manual_common_name" not in _columns():
        op.add_column(
            "taxonomy_cache",
            sa.Column("manual_common_name", sa.String(length=120), nullable=True),
        )


def downgrade() -> None:
    if "manual_common_name" in _columns():
        with op.batch_alter_table("taxonomy_cache", schema=None) as batch_op:
            batch_op.drop_column("manual_common_name")
