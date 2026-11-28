"""Record whether a capture's snapshot and video readings name the same bird (#804).

When the video reading finishes, YA-WAMF compares it with the capture's first
reading by catalogue species (``app/services/reading_agreement.py``) and keeps the
outcome here: ``agree``, ``disagree`` or ``cannot_compare``. A disagreement is shown
on the record as needing a person.

Additive and nullable. Existing rows stay NULL, which means the readings were never
compared; nothing is guessed for them here. Downgrade removes the column alone.

Revision ID: e8c3a51f9d24
Revises: d4b8f2a6c1e3
"""

from alembic import op
import sqlalchemy as sa

revision = "e8c3a51f9d24"
down_revision = "d4b8f2a6c1e3"
branch_labels = None
depends_on = None

COLUMN = "reading_agreement"


def _has_column() -> bool:
    return COLUMN in {row[1] for row in op.get_bind().execute(sa.text("PRAGMA table_info(detections)"))}


def upgrade() -> None:
    if _has_column():
        return
    # The values match READING_AGREEMENTS in app/services/reading_agreement.py.
    op.execute(
        f"ALTER TABLE detections ADD COLUMN {COLUMN} TEXT "
        f"CHECK ({COLUMN} IS NULL OR {COLUMN} IN ('agree', 'disagree', 'cannot_compare'))"
    )


def downgrade() -> None:
    # Rebuilding detections would disrupt its evidence triggers and foreign keys.
    if _has_column():
        op.execute(f"ALTER TABLE detections DROP COLUMN {COLUMN}")
