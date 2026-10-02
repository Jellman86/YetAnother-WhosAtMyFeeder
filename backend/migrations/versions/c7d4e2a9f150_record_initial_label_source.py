"""Record when a detection's first label was borrowed from Frigate.

Revision ID: c7d4e2a9f150
Revises: a41f928b0d72

A trusted Frigate sub-label can become the stored species when YA-WAMF's own
classifier stays below threshold. Later video analysis must know that the label
is not YA-WAMF's own identification. Existing rows stay NULL: their source was
never recorded and is not guessed.
"""

from alembic import op
import sqlalchemy as sa

revision = "c7d4e2a9f150"
down_revision = "a41f928b0d72"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    rows = op.get_bind().execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    if "label_source" not in _columns("detection_initial_classifications"):
        op.add_column("detection_initial_classifications", sa.Column("label_source", sa.Text(), nullable=True))


def downgrade() -> None:
    # A batch rebuild would rename the table under capture_initial_classification,
    # which SQLite rejects; the trigger never names this column, so drop it in place.
    if "label_source" in _columns("detection_initial_classifications"):
        op.execute("ALTER TABLE detection_initial_classifications DROP COLUMN label_source")
