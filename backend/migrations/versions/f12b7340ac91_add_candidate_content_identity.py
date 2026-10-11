"""Retain content identity for bounded photo comparisons.

Revision ID: f12b7340ac91
Revises: e98a7230bd14
"""

from alembic import op
import sqlalchemy as sa

revision = "f12b7340ac91"
down_revision = "e98a7230bd14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("snapshot_candidates")}
    if "content_sha256" not in columns:
        op.add_column("snapshot_candidates", sa.Column("content_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("snapshot_candidates")}
    if "content_sha256" in columns:
        # Keep visit-integrity triggers attached to their original table.
        op.drop_column("snapshot_candidates", "content_sha256")
