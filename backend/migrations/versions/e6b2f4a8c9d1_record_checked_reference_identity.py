"""Record which cached reference descriptions had their taxon checked.

A cached Wikipedia summary cannot be checked against its taxon from its text:
the REST extract leaves the scientific name out. The description is checked
when it is fetched, through the article the taxon's own record links to, and
this column keeps that fact with the row. Existing rows are unchecked (0) and
are looked up again the first time they are read. Downgrade removes the column
alone; every cached description is kept.

Revision ID: e6b2f4a8c9d1
Revises: d4a7c1e92b36
"""

from alembic import op
import sqlalchemy as sa

revision = "e6b2f4a8c9d1"
down_revision = "d4a7c1e92b36"
branch_labels = None
depends_on = None

TABLE = "species_info_cache"
COLUMN = "identity_checked"


def _has_column() -> bool:
    return COLUMN in {row[1] for row in op.get_bind().execute(sa.text(f"PRAGMA table_info({TABLE})"))}


def upgrade() -> None:
    if _has_column():
        return
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} BOOLEAN NOT NULL DEFAULT 0")


def downgrade() -> None:
    if _has_column():
        op.execute(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}")
