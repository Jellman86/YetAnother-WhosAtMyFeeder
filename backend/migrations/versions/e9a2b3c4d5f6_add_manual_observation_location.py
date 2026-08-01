"""Add retained location metadata to manual observations.

Revision ID: e9a2b3c4d5f6
Revises: d8f1a2b3c4e5
Create Date: 2026-08-01 11:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9a2b3c4d5f6"
down_revision: Union[str, None] = "d8f1a2b3c4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    rows = op.get_bind().execute(sa.text("PRAGMA table_info(manual_observation_drafts)")).fetchall()
    return {str(row[1]) for row in rows}


def upgrade() -> None:
    columns = _columns()
    if "latitude" not in columns:
        op.add_column("manual_observation_drafts", sa.Column("latitude", sa.Float(), nullable=True))
    if "longitude" not in columns:
        op.add_column("manual_observation_drafts", sa.Column("longitude", sa.Float(), nullable=True))
    if "location_source" not in columns:
        op.add_column("manual_observation_drafts", sa.Column("location_source", sa.String(length=32), nullable=True))


def downgrade() -> None:
    columns = _columns()
    with op.batch_alter_table("manual_observation_drafts", schema=None) as batch_op:
        if "location_source" in columns:
            batch_op.drop_column("location_source")
        if "longitude" in columns:
            batch_op.drop_column("longitude")
        if "latitude" in columns:
            batch_op.drop_column("latitude")
