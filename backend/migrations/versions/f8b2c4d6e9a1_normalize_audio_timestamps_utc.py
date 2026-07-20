"""Normalize BirdNET timestamps to naive UTC.

Revision ID: f8b2c4d6e9a1
Revises: e7a1c9d4b2f6
Create Date: 2026-07-20 20:20:00.000000
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8b2c4d6e9a1"
down_revision: Union[str, None] = "e7a1c9d4b2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _canonical_timestamp(value: object) -> str | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat(sep=" ")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "audio_detections" not in inspector.get_table_names():
        return

    rows = bind.execute(sa.text("SELECT id, timestamp FROM audio_detections")).fetchall()
    updates: list[dict[str, object]] = []
    for row in rows:
        canonical = _canonical_timestamp(row[1])
        if canonical is not None and canonical != str(row[1]):
            updates.append({"row_id": row[0], "timestamp": canonical})

    if updates:
        bind.execute(
            sa.text("UPDATE audio_detections SET timestamp = :timestamp WHERE id = :row_id"),
            updates,
        )


def downgrade() -> None:
    # Offset information cannot be reconstructed after canonicalization.
    pass
