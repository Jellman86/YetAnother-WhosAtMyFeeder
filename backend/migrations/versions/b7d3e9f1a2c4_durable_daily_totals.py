"""Keep per-day species totals that outlive the detections they were counted from (#949).

Retention cleanup deletes detection rows, and every chart that counted those rows lost the
days with them. Four tables keep the history instead:

- ``daily_totals_days``: days whose totals are sealed. Every age cleanup (scheduled or "Purge Old
  Records") seals a day from its rows, and commits that, before it deletes any of them; from then
  on the day's totals are kept as they were. ``complete`` is 0 for a day that began before
  tracking started, whose rows may already have been thinned without a record.
- ``species_daily_totals``: captures and visits per sealed instance-local day and canonical
  species.
- ``lost_captures``: one row per capture deleted because Frigate no longer has its event, written
  in the same transaction as the delete. Its day stays live, and the row is counted with it until
  the day is sealed, when it is folded into the day's total.
- ``daily_totals_tracking``: the one instant tracking started, set by this upgrade.

A live day is read from its rows (and lost captures), a sealed day from its totals, so the two
never count the same capture twice. The tables start empty: every stored row is still there to
read, and each day is written from those rows at the moment it would otherwise begin to disappear.

Downgrade drops these tables. Detection rows are never touched, but for every day cleanup has
already removed, these totals are the only copy of its counts: a downgrade deletes them, and they
cannot be rebuilt from the rows that are left.

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
        CREATE TABLE IF NOT EXISTS daily_totals_tracking (
            id INTEGER NOT NULL PRIMARY KEY CHECK (id = 1),
            started_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute(
        "INSERT OR IGNORE INTO daily_totals_tracking (id, started_at) VALUES (1, strftime('%Y-%m-%d %H:%M:%S', 'now'))"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_totals_days (
            day DATE NOT NULL PRIMARY KEY,
            sealed_at TIMESTAMP NOT NULL,
            complete INTEGER NOT NULL CHECK (complete IN (0, 1))
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
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lost_captures (
            frigate_event TEXT NOT NULL PRIMARY KEY,
            detection_time TIMESTAMP NOT NULL,
            species_key TEXT NOT NULL,
            species_id INTEGER,
            taxa_id INTEGER,
            scientific_name TEXT,
            common_name TEXT,
            display_name TEXT NOT NULL,
            lost_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_lost_captures_time ON lost_captures (detection_time)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_lost_captures_time")
    op.execute("DROP TABLE IF EXISTS lost_captures")
    op.execute("DROP INDEX IF EXISTS idx_species_daily_totals_species")
    op.execute("DROP TABLE IF EXISTS species_daily_totals")
    op.execute("DROP TABLE IF EXISTS daily_totals_days")
    op.execute("DROP TABLE IF EXISTS daily_totals_tracking")
