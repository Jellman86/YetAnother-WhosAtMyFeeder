"""Keep per-day species totals that outlive the detections they were counted from (#949).

Retention cleanup deletes detection rows, and every chart that counted those rows lost the
days with them. Two tables keep the history instead:

- ``daily_totals_days``: days whose totals are sealed. Automatic cleanup seals a day from its
  rows, and commits that, before it deletes any of them; from then on the day's
  totals are kept as they were. ``complete`` is 0 when some of the day's rows were already gone
  before it was sealed (history from before this table existed), so no chart claims more than
  was counted. ``cleanup_cutoff`` is the cleanup instant that sealed it, null for a day sealed
  because Frigate lost one of its events.
- ``species_daily_totals``: captures and visits per sealed instance-local day and canonical
  species.

A day that is not sealed still has all its rows and is read from them, so the two never count
the same capture twice. The tables start empty: every stored row is still there to read, and
each day is written from those rows at the moment it would otherwise begin to disappear.

Downgrade drops both tables. Detection rows are never touched.

Revision ID: b7d3e9f1a2c4
Revises: e6b2f4a8c9d1
"""

from alembic import op

revision = "b7d3e9f1a2c4"
down_revision = "e6b2f4a8c9d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_totals_days (
            day DATE NOT NULL PRIMARY KEY,
            sealed_at TIMESTAMP NOT NULL,
            complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
            cleanup_cutoff TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS species_daily_totals (
            day DATE NOT NULL REFERENCES daily_totals_days (day) ON DELETE CASCADE,
            species_key TEXT NOT NULL,
            species_id INTEGER,
            taxa_id INTEGER,
            scientific_name TEXT,
            common_name TEXT,
            display_name TEXT NOT NULL,
            capture_count INTEGER NOT NULL CHECK (capture_count > 0),
            visit_count INTEGER NOT NULL CHECK (visit_count >= 0 AND visit_count <= capture_count),
            CONSTRAINT pk_species_daily_totals PRIMARY KEY (day, species_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_species_daily_totals_species ON species_daily_totals (species_key, day)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_species_daily_totals_species")
    op.execute("DROP TABLE IF EXISTS species_daily_totals")
    op.execute("DROP TABLE IF EXISTS daily_totals_days")
