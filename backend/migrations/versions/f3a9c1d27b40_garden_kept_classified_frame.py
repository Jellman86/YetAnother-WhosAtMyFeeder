"""Let Garden keep YA-WAMF's own copy of the whole frame its bird model classified.

Frigate discards a stationary bird's event, snapshot and all, within minutes. A chicken moved from
bird history to Garden after that had no photo, though YA-WAMF still held the frame it classified.
The new ``classified_frame`` photo source records that the kept photo is that copy rather than one
fetched from Frigate.

Downgrade relabels such a kept photo ``frigate_snapshot``, the only other source an older version
knows for a Frigate event: the bytes were Frigate's frame, the file stays and is still served.

Revision ID: f3a9c1d27b40
Revises: b7d3e9f1a2c4
"""

from alembic import op
import sqlalchemy as sa

revision = "f3a9c1d27b40"
down_revision = "b7d3e9f1a2c4"
branch_labels = None
depends_on = None

TABLE = "garden_kept_media"
CHECK = "ck_garden_kept_photo"
KEPT_PHOTO = (
    "(photo_state='kept' AND COALESCE(photo_source, '') IN ({sources})"
    " AND COALESCE(length(photo_sha256), 0)=64 AND COALESCE(photo_bytes, 0) > 0)"
    " OR (photo_state!='kept' AND photo_sha256 IS NULL AND photo_bytes IS NULL)"
)
WITH_CLASSIFIED_FRAME = KEPT_PHOTO.format(sources="'frigate_snapshot','motion_photo','classified_frame'")
WITHOUT_CLASSIFIED_FRAME = KEPT_PHOTO.format(sources="'frigate_snapshot','motion_photo'")


def _check_sql() -> str:
    row = (
        op.get_bind()
        .execute(sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"), {"name": TABLE})
        .fetchone()
    )
    return str(row[0]) if row else ""


def _replace_check(expression: str) -> None:
    with op.batch_alter_table(TABLE, recreate="always") as batch:
        batch.drop_constraint(CHECK, type_="check")
        batch.create_check_constraint(CHECK, expression)


def upgrade() -> None:
    table_sql = _check_sql()
    if not table_sql or "classified_frame" in table_sql:
        return
    _replace_check(WITH_CLASSIFIED_FRAME)


def downgrade() -> None:
    table_sql = _check_sql()
    if not table_sql or "classified_frame" not in table_sql:
        return
    op.execute("UPDATE garden_kept_media SET photo_source='frigate_snapshot' WHERE photo_source='classified_frame'")
    _replace_check(WITHOUT_CLASSIFIED_FRAME)
