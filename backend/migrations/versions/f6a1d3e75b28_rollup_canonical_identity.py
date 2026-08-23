"""Re-key the daily rollup on catalogue identity

`species_daily_rollup` is the one place the grouping key is persisted rather
than recomputed on read, and it forms half the primary key. Live grouping moved
to a namespaced, identity-first key; the rollup was pinned to the old format so
the table would not end up holding two formats either side of an upgrade.

Rebuilding the table from detections is not available as a remedy. On a live
install 29 rollup rows covering 97 detections predate the oldest surviving
detection, so the rollup is the only remaining record of them and discarding it
would lose history.

So the keys are rewritten in place, and identity is resolved from `detections`
rather than the catalogue: it keeps the migration inside one database, and the
identity a row should carry is the one history actually recorded for it. A row
whose detections are gone keeps a text key, which is honest, because nothing
here knows what it was.

Measured on that install before writing this: 193 rows, 150 resolvable, 43
keeping a text key, and no primary key collisions. Collisions are still handled,
because another install is not this one.

Revision ID: f6a1d3e75b28
Revises: e2b8c47f91a3
Create Date: 2026-08-23
"""

import sqlalchemy as sa
from alembic import op

revision = "f6a1d3e75b28"
down_revision = "e2b8c47f91a3"
branch_labels = None
depends_on = None

_TABLE = "species_daily_rollup"

# Mirrors `DetectionRepository._canonical_key_sql`, against the rollup's own
# columns. `r.species_id` is filled immediately above from detections.
_NEW_KEY = """
    COALESCE(
        'species:' || CAST(r.species_id AS TEXT),
        'taxon:' || CAST(r.taxa_id AS TEXT),
        'name:' || LOWER(r.scientific_name),
        'label:' || LOWER(r.display_name)
    )
"""

_LEGACY_KEY = """
    COALESCE(
        CAST(r.taxa_id AS TEXT),
        LOWER(r.scientific_name),
        LOWER(r.display_name)
    )
"""


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(existing["name"] == column for existing in inspector.get_columns(table))


def _table_exists(table: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table in inspector.get_table_names()


def _rebuild_with_key(key_expression: str) -> None:
    """Rewrite every key, merging any rows that collide on the new one.

    Done as a rebuild rather than an UPDATE because the key is half the primary
    key: an UPDATE would fail part-way through on a collision, while a rebuild
    resolves one by construction.

    `camera_count` is a count of distinct cameras, so merged rows take the
    largest rather than the sum. Summing would overstate whenever two merged
    rows saw the same camera, and overstating is the worse error.
    """
    op.execute(f"ALTER TABLE {_TABLE} RENAME TO {_TABLE}_old")
    op.execute(
        f"""
        CREATE TABLE {_TABLE} (
            rollup_date DATE NOT NULL,
            canonical_key VARCHAR NOT NULL,
            display_name VARCHAR NOT NULL,
            scientific_name VARCHAR,
            common_name VARCHAR,
            taxa_id INTEGER,
            species_id INTEGER,
            detection_count INTEGER NOT NULL,
            camera_count INTEGER NOT NULL,
            avg_confidence FLOAT,
            max_confidence FLOAT,
            min_confidence FLOAT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            CONSTRAINT pk_species_daily_rollup PRIMARY KEY (rollup_date, canonical_key)
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO {_TABLE} (
            rollup_date, canonical_key, display_name, scientific_name, common_name,
            taxa_id, species_id, detection_count, camera_count,
            avg_confidence, max_confidence, min_confidence, first_seen, last_seen
        )
        SELECT
            r.rollup_date,
            {key_expression} AS canonical_key,
            MIN(r.display_name),
            MAX(r.scientific_name),
            MAX(r.common_name),
            MAX(r.taxa_id),
            MAX(r.species_id),
            SUM(r.detection_count),
            MAX(r.camera_count),
            -- Weighted by how many detections each merged row represents, so a
            -- day with one sighting cannot outweigh a day with fifty.
            CASE WHEN SUM(r.detection_count) > 0
                 THEN SUM(COALESCE(r.avg_confidence, 0) * r.detection_count) / SUM(r.detection_count)
                 END,
            MAX(r.max_confidence),
            MIN(r.min_confidence),
            MIN(r.first_seen),
            MAX(r.last_seen)
        FROM {_TABLE}_old r
        GROUP BY r.rollup_date, {key_expression}
        """
    )
    op.execute(f"DROP TABLE {_TABLE}_old")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_species_rollup_canonical ON {_TABLE} (canonical_key)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_species_rollup_date ON {_TABLE} (rollup_date)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_species_rollup_display ON {_TABLE} (display_name)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_species_rollup_species_id ON {_TABLE} (species_id)")


def upgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if not _has_column(_TABLE, "species_id"):
        op.add_column(_TABLE, sa.Column("species_id", sa.Integer(), nullable=True))

    # Identity comes from what history recorded, not from the catalogue, so the
    # migration stays inside one database. A row whose detections are gone
    # simply keeps a text key.
    # Only when history is unanimous. `MIN()` over several candidates would be a
    # guess, and nothing else in this phase guesses: a row matching more than
    # one identity keeps a text key, exactly as a row with no match does.
    match_clause = """
        d.species_id IS NOT NULL
        AND (
            (r.scientific_name IS NOT NULL AND LOWER(d.scientific_name) = LOWER(r.scientific_name))
            OR (r.taxa_id IS NOT NULL AND d.taxa_id = r.taxa_id)
            OR LOWER(d.display_name) = LOWER(r.display_name)
        )
    """
    op.execute(
        f"""
        UPDATE {_TABLE} AS r SET species_id = (
            SELECT MIN(d.species_id) FROM detections d WHERE {match_clause}
        )
        WHERE r.species_id IS NULL
          AND (SELECT COUNT(DISTINCT d.species_id) FROM detections d WHERE {match_clause}) = 1
        """
    )
    _rebuild_with_key(_NEW_KEY)


def downgrade() -> None:
    if not _table_exists(_TABLE):
        return
    _rebuild_with_key(_LEGACY_KEY)
    # The rebuild recreates every index, including the one on `species_id`.
    # SQLite refuses to drop a column an index still references, so that index
    # goes first.
    op.execute("DROP INDEX IF EXISTS idx_species_rollup_species_id")
    if _has_column(_TABLE, "species_id"):
        op.drop_column(_TABLE, "species_id")
