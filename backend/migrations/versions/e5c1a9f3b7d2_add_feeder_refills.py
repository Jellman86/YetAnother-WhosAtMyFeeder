"""Record feeder refills, so a jump in visits after one can be read for what it is (#946).

A new table beside the detection history; nothing in ``detections`` or the rollups changes. A
refill has a time in UTC, an optional camera, where it came from (recorded by hand, sent to the
API, or, later, over MQTT) and an optional note. An automation's own event id is unique, so the
same event sent twice is one refill. A cooldown-suppressed event id also points to the refill
it repeated.

Downgrade removes the refill markers and their automation event ids. Detection history is preserved.

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
ALIASES = "feeder_refill_event_aliases"
TIME_INDEX = "idx_feeder_refills_refilled_at"
ALIAS_REFILL_INDEX = "idx_feeder_refill_event_aliases_refill_id"


def upgrade() -> None:
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
        # A retried DELETE must never find a different refill at the same id.
        sqlite_autoincrement=True,
        if_not_exists=True,
    )
    op.create_index(TIME_INDEX, TABLE, ["refilled_at"], unique=False, if_not_exists=True)
    op.create_table(
        ALIASES,
        sa.Column("source_event_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("refill_id", sa.Integer(), sa.ForeignKey(f"{TABLE}.id", ondelete="CASCADE"), nullable=False),
        if_not_exists=True,
    )
    op.create_index(ALIAS_REFILL_INDEX, ALIASES, ["refill_id"], unique=False, if_not_exists=True)


def downgrade() -> None:
    op.drop_table(ALIASES, if_exists=True)
    op.drop_table(TABLE, if_exists=True)
