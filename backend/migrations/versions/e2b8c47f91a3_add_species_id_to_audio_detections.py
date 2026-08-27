"""Give audio detections a place to record catalogue identity

Audio correlation is the last read path still keyed on name text. BirdNET-Go
reports a scientific name, and a scientific name moves: measured on a live
install, 84 of 85 species it reports resolve to a catalogue identity, and the
one that does not is `Corvus monedula`, which IOC 14.2 calls `Coloeus monedula`
after the jackdaw genus split. Two sources, opposite sides of one rename, and
nothing to say they are the same bird.

Nullable and additive. A row whose name resolves to exactly one identity gains
it; an ambiguous or unknown name keeps nothing, which is the same rule the
detection backfill follows.

Revision ID: e2b8c47f91a3
Revises: d5e7a91c2f38
Create Date: 2026-08-23
"""

import sqlalchemy as sa
from alembic import op

revision = "e2b8c47f91a3"
down_revision = "d5e7a91c2f38"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(existing["name"] == column for existing in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_column("audio_detections", "species_id"):
        op.add_column("audio_detections", sa.Column("species_id", sa.Integer(), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS idx_audio_detections_species_id ON audio_detections (species_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audio_detections_species_id")
    if _has_column("audio_detections", "species_id"):
        op.drop_column("audio_detections", "species_id")
