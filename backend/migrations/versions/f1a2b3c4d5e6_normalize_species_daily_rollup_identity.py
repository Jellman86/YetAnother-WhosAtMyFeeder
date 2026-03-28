"""normalize_species_daily_rollup_identity

Revision ID: f1a2b3c4d5e6
Revises: e1a4b5c6d7e8
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e1a4b5c6d7e8"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": name},
        ).fetchone()
        is not None
    )


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _index_names(conn, table: str) -> set[str]:
    rows = conn.execute(sa.text(f"PRAGMA index_list({table})")).fetchall()
    return {row[1] for row in rows}


def _create_rollup_table() -> None:
    op.create_table(
        "species_daily_rollup_new",
        sa.Column("rollup_date", sa.Date(), nullable=False),
        sa.Column("canonical_key", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("scientific_name", sa.String(), nullable=True),
        sa.Column("common_name", sa.String(), nullable=True),
        sa.Column("taxa_id", sa.Integer(), nullable=True),
        sa.Column("detection_count", sa.Integer(), nullable=False),
        sa.Column("camera_count", sa.Integer(), nullable=False),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("max_confidence", sa.Float(), nullable=True),
        sa.Column("min_confidence", sa.Float(), nullable=True),
        sa.Column("first_seen", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_seen", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("rollup_date", "canonical_key", name="pk_species_daily_rollup"),
    )


def upgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "species_daily_rollup") and "canonical_key" in _column_names(conn, "species_daily_rollup"):
        indexes = _index_names(conn, "species_daily_rollup")
        if "idx_species_rollup_date" not in indexes:
            op.create_index("idx_species_rollup_date", "species_daily_rollup", ["rollup_date"], unique=False)
        if "idx_species_rollup_canonical" not in indexes:
            op.create_index("idx_species_rollup_canonical", "species_daily_rollup", ["canonical_key"], unique=False)
        if "idx_species_rollup_display" not in indexes:
            op.create_index("idx_species_rollup_display", "species_daily_rollup", ["display_name"], unique=False)
        return

    if _table_exists(conn, "species_daily_rollup_new"):
        op.execute("DROP TABLE IF EXISTS species_daily_rollup_new")

    _create_rollup_table()

    if _table_exists(conn, "detections"):
        op.execute(
            """
            INSERT INTO species_daily_rollup_new (
                rollup_date,
                canonical_key,
                display_name,
                scientific_name,
                common_name,
                taxa_id,
                detection_count,
                camera_count,
                avg_confidence,
                max_confidence,
                min_confidence,
                first_seen,
                last_seen
            )
            WITH enriched AS (
                SELECT
                    date(d.detection_time) AS rollup_date,
                    d.display_name AS display_name,
                    COALESCE(d.scientific_name, tc.scientific_name) AS scientific_name,
                    COALESCE(d.common_name, tc.common_name) AS common_name,
                    COALESCE(d.taxa_id, tc.taxa_id) AS taxa_id,
                    d.camera_name AS camera_name,
                    d.score AS score,
                    d.detection_time AS detection_time,
                    COALESCE(
                        CAST(COALESCE(d.taxa_id, tc.taxa_id) AS TEXT),
                        LOWER(COALESCE(d.scientific_name, tc.scientific_name)),
                        LOWER(d.display_name)
                    ) AS canonical_key
                FROM detections d
                LEFT JOIN taxonomy_cache tc
                    ON (
                        (d.scientific_name IS NOT NULL AND LOWER(tc.scientific_name) = LOWER(d.scientific_name))
                        OR (
                            d.scientific_name IS NULL
                            AND (
                                LOWER(tc.scientific_name) = LOWER(d.display_name)
                                OR LOWER(tc.common_name) = LOWER(d.display_name)
                            )
                        )
                    )
                WHERE (d.is_hidden = 0 OR d.is_hidden IS NULL)
            )
            SELECT
                rollup_date,
                canonical_key,
                COALESCE(
                    MAX(CASE
                        WHEN common_name IS NOT NULL AND LOWER(display_name) = LOWER(common_name) THEN display_name
                    END),
                    MAX(common_name),
                    MIN(display_name)
                ) AS display_name,
                MAX(scientific_name) AS scientific_name,
                MAX(common_name) AS common_name,
                MAX(taxa_id) AS taxa_id,
                COUNT(*) AS detection_count,
                COUNT(DISTINCT camera_name) AS camera_count,
                AVG(score) AS avg_confidence,
                MAX(score) AS max_confidence,
                MIN(score) AS min_confidence,
                MIN(detection_time) AS first_seen,
                MAX(detection_time) AS last_seen
            FROM enriched
            GROUP BY rollup_date, canonical_key
            """
        )

    op.execute("DROP TABLE IF EXISTS species_daily_rollup")
    op.execute("ALTER TABLE species_daily_rollup_new RENAME TO species_daily_rollup")
    op.create_index("idx_species_rollup_date", "species_daily_rollup", ["rollup_date"], unique=False)
    op.create_index("idx_species_rollup_canonical", "species_daily_rollup", ["canonical_key"], unique=False)
    op.create_index("idx_species_rollup_display", "species_daily_rollup", ["display_name"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "species_daily_rollup_old"):
        op.execute("DROP TABLE IF EXISTS species_daily_rollup_old")

    op.create_table(
        "species_daily_rollup_old",
        sa.Column("rollup_date", sa.Date(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("detection_count", sa.Integer(), nullable=False),
        sa.Column("camera_count", sa.Integer(), nullable=False),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("max_confidence", sa.Float(), nullable=True),
        sa.Column("min_confidence", sa.Float(), nullable=True),
        sa.Column("first_seen", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_seen", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("rollup_date", "display_name", name="pk_species_daily_rollup"),
    )

    if _table_exists(conn, "species_daily_rollup"):
        op.execute(
            """
            INSERT INTO species_daily_rollup_old (
                rollup_date,
                display_name,
                detection_count,
                camera_count,
                avg_confidence,
                max_confidence,
                min_confidence,
                first_seen,
                last_seen
            )
            SELECT
                rollup_date,
                display_name,
                detection_count,
                camera_count,
                avg_confidence,
                max_confidence,
                min_confidence,
                first_seen,
                last_seen
            FROM species_daily_rollup
            """
        )

    op.execute("DROP INDEX IF EXISTS idx_species_rollup_canonical")
    op.execute("DROP INDEX IF EXISTS idx_species_rollup_display")
    op.execute("DROP INDEX IF EXISTS idx_species_rollup_date")
    op.execute("DROP TABLE IF EXISTS species_daily_rollup")
    op.execute("ALTER TABLE species_daily_rollup_old RENAME TO species_daily_rollup")
    op.create_index("idx_species_rollup_date", "species_daily_rollup", ["rollup_date"], unique=False)
    op.create_index("idx_species_rollup_display", "species_daily_rollup", ["display_name"], unique=False)
