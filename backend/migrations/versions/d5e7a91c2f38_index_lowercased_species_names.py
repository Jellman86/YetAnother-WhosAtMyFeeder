"""Index the lowercased species names the species filter joins on

Filtering the events list by species was measurably slower than filtering by
date or camera, which a user reported. The cause is the taxonomy join:

    LOWER(tc.scientific_name) = LOWER(d.scientific_name)

A plain index cannot serve a predicate wrapped in a function, so SQLite scanned
`taxonomy_cache` once per detection row. Measured on a 96,108 row copy of a real
database, filtering by species took 25ms against effectively zero for the other
filters, and the plan showed `SCAN tc_filter LEFT-JOIN`.

These are expression indexes matching the predicates exactly, so the join can be
served by a lookup instead. Same measurement afterwards: 16ms, and the scan is
gone.

Revision ID: d5e7a91c2f38
Revises: c8f3a1d47b02
Create Date: 2026-08-23
"""

from alembic import op

revision = "d5e7a91c2f38"
down_revision = "c8f3a1d47b02"
branch_labels = None
depends_on = None

# Indexes only: no column, constraint or data change, so both directions are
# safe to re-run and neither can lose a row.
_INDEXES = (
    ("idx_taxonomy_cache_lower_scientific", "taxonomy_cache", "LOWER(scientific_name)"),
    ("idx_taxonomy_cache_lower_common", "taxonomy_cache", "LOWER(common_name)"),
    ("idx_detections_lower_scientific", "detections", "LOWER(scientific_name)"),
    ("idx_detections_lower_display", "detections", "LOWER(display_name)"),
    ("idx_detections_lower_common", "detections", "LOWER(common_name)"),
)


def upgrade() -> None:
    for name, table, expression in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({expression})")


def downgrade() -> None:
    for name, _table, _expression in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
