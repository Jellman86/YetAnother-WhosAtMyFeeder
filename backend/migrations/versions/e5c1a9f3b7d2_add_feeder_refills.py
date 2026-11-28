"""Record feeder refills, so a jump in visits after one can be read for what it is (#946).

A new table beside the detection history; nothing in ``detections`` or the rollups changes. A
refill has a time in UTC, an optional camera, where it came from (recorded by hand, sent to the
API, or, later, over MQTT) and an optional note. An automation's own event id is unique, so the
same event sent twice is one refill.

Downgrade drops the table and the refills in it. They are the owner's markers, not detections,
and the release that reads them goes with it.

Revision ID: e5c1a9f3b7d2
Revises: d4b8f2a6c1e3
"""

import sqlalchemy as sa
from alembic import op

revision = "e5c1a9f3b7d2"
down_revision = "d4b8f2a6c1e3"
branch_labels = None
depends_on = None

TABLE = "feeder_refills"
TIME_INDEX = "idx_feeder_refills_refilled_at"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("refilled_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("camera_name", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("source_event_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_event_id", name="uq_feeder_refills_source_event_id"),
        sa.CheckConstraint("source IN ('manual','api','mqtt')", name="ck_feeder_refills_source"),
    )
    op.create_index(TIME_INDEX, TABLE, ["refilled_at"], unique=False)


def downgrade() -> None:
    if TABLE not in _tables():
        return
    op.drop_index(TIME_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
