"""Preserve first classification without inventing historical provenance.

Revision ID: a41f928b0d72
Revises: f12b7340ac91
"""

from alembic import op

revision = "a41f928b0d72"
down_revision = "f12b7340ac91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS detection_initial_classifications (
            detection_id INTEGER PRIMARY KEY REFERENCES detections(id) ON DELETE CASCADE,
            category_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            scientific_name TEXT,
            common_name TEXT,
            score FLOAT NOT NULL,
            detection_index INTEGER NOT NULL,
            model_artifact_id INTEGER,
            model_output_index INTEGER
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS detection_species_choices (
            detection_id INTEGER PRIMARY KEY REFERENCES detections(id) ON DELETE CASCADE,
            category_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            scientific_name TEXT,
            common_name TEXT
        )
    """)
    # Every insertion path captures the same atomic first evidence. Updates,
    # duplicate ingestion and upgrades cannot turn a later label into history.
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS capture_initial_classification
        AFTER INSERT ON detections BEGIN
            INSERT INTO detection_initial_classifications
                (detection_id, category_name, display_name, scientific_name, common_name,
                 score, detection_index, model_artifact_id, model_output_index)
            VALUES (NEW.id, NEW.category_name, NEW.display_name, NEW.scientific_name, NEW.common_name,
                    NEW.score, NEW.detection_index, NEW.model_artifact_id, NEW.model_output_index);
        END
    """)
    # SQLite maintenance connections may not enable foreign keys. Match the
    # visit-media cleanup contract so recycled IDs never inherit old evidence.
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS delete_initial_classification
        AFTER DELETE ON detections BEGIN
            DELETE FROM detection_initial_classifications WHERE detection_id = OLD.id;
            DELETE FROM detection_species_choices WHERE detection_id = OLD.id;
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS delete_initial_classification")
    op.execute("DROP TRIGGER IF EXISTS capture_initial_classification")
    op.execute("DROP TABLE IF EXISTS detection_initial_classifications")
    op.execute("DROP TABLE IF EXISTS detection_species_choices")
