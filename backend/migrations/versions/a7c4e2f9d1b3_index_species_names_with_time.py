"""Give each species column a (name, time) index so a rare species is a seek

Filtering the events list by a rare species read almost the whole table: the
query orders by time and asks for one page, so for a species with thousands
of rows the newest fifty are found immediately, while for a species with
eighty the walk back through the time index visits nearly every row before
the page fills (#258, confirmed by the reporter with a date-range probe).

These composite expression indexes let every branch of the species filter
produce its own newest-first candidates by seek - (name, time) per species
column, plus (taxa_id, time) which previously had no index at all and forced
the alias resolver's OR into a full scan on every filtered request. ANALYZE
records the table shape so the planner keeps choosing them.

Revision ID: a7c4e2f9d1b3
Revises: f6a1d3e75b28
Create Date: 2026-08-31
"""

from alembic import op

revision = "a7c4e2f9d1b3"
down_revision = "f6a1d3e75b28"
branch_labels = None
depends_on = None

# Indexes only: no column, constraint or data change, so both directions are
# safe to re-run and neither can lose a row.
_INDEXES = (
    ("idx_detections_lower_display_time", "detections", "LOWER(display_name), detection_time"),
    ("idx_detections_lower_scientific_time", "detections", "LOWER(scientific_name), detection_time"),
    ("idx_detections_lower_common_time", "detections", "LOWER(common_name), detection_time"),
    ("idx_detections_taxa_time", "detections", "taxa_id, detection_time"),
)


def upgrade() -> None:
    for name, table, expression in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({expression})")
    op.execute("ANALYZE")


def downgrade() -> None:
    for name, _table, _expression in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
