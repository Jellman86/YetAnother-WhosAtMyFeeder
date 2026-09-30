"""Index retained BirdNET identities without trusting malformed JSON.

Revision ID: e98a7230bd14
Revises: e8b2c4d6f0a1
Create Date: 2026-09-30
"""

from alembic import op

revision = "e98a7230bd14"
down_revision = "e8b2c4d6f0a1"
branch_labels = None
depends_on = None

_KEYS = ("detectionId", "detection_id", "id")


def upgrade() -> None:
    # Match the authorization query exactly so SQLite can combine all three
    # indexes. Hidden tombstones participate even outside the public interval.
    payload = "CASE WHEN json_valid(raw_data) THEN raw_data ELSE '{}' END"
    for key in _KEYS:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_audio_birdnet_{key} ON audio_detections "
            f"(CAST(json_extract({payload}, '$.{key}') AS INTEGER))"
        )


def downgrade() -> None:
    for key in reversed(_KEYS):
        op.execute(f"DROP INDEX IF EXISTS idx_audio_birdnet_{key}")
