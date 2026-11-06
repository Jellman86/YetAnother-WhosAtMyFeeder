"""Preserve classifier input evidence without inventing historical sources.

Revision ID: d2f643a11e00
Revises: b91a6e2d4c80
"""

from alembic import op
import sqlalchemy as sa

revision = "d2f643a11e00"
down_revision = "b91a6e2d4c80"
branch_labels = None
depends_on = None


def _capture_trigger(include_input: bool) -> None:
    op.execute("DROP TRIGGER IF EXISTS capture_initial_classification")
    column = ", classification_input_json" if include_input else ""
    value = ", NEW.classification_input_json" if include_input else ""
    op.execute(f"""
        CREATE TRIGGER capture_initial_classification AFTER INSERT ON detections BEGIN
            INSERT INTO detection_initial_classifications
                (detection_id, category_name, display_name, scientific_name, common_name,
                 score, detection_index, model_artifact_id, model_output_index{column})
            VALUES (NEW.id, NEW.category_name, NEW.display_name, NEW.scientific_name, NEW.common_name,
                    NEW.score, NEW.detection_index, NEW.model_artifact_id, NEW.model_output_index{value});
        END
    """)


def upgrade() -> None:
    for table in ("detections", "detection_initial_classifications"):
        columns = {row[1] for row in op.get_bind().execute(sa.text(f"PRAGMA table_info({table})"))}
        if "classification_input_json" not in columns:
            op.add_column(table, sa.Column("classification_input_json", sa.Text(), nullable=True))
    _capture_trigger(True)


def downgrade() -> None:
    _capture_trigger(False)
    # Rebuilding detections would disrupt other evidence triggers and foreign keys.
    for table in ("detection_initial_classifications", "detections"):
        columns = {row[1] for row in op.get_bind().execute(sa.text(f"PRAGMA table_info({table})"))}
        if "classification_input_json" in columns:
            op.execute(f"ALTER TABLE {table} DROP COLUMN classification_input_json")
