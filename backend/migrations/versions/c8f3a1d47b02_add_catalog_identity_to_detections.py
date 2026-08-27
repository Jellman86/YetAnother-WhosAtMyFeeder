"""add catalog identity to detections

Phase 3 of the versioned species catalogue: detections gain nullable
canonical-identity and provenance columns. `species_id` is the opaque
catalogue identity, written only when the catalogue and the label path agree;
`model_artifact_id` and `model_output_index` record which artifact and output
produced the classification. The existing name snapshot columns are untouched
and remain the historical record. No cross-database foreign keys, by design.

Revision ID: c8f3a1d47b02
Revises: b4e1c9d27a30
Create Date: 2026-08-21 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8f3a1d47b02"
down_revision: Union[str, None] = "b4e1c9d27a30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("species_id", "model_artifact_id", "model_output_index")


def _existing_columns(inspector: sa.Inspector) -> set[str]:
    return {column["name"] for column in inspector.get_columns("detections")}


def _has_index(inspector: sa.Inspector, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes("detections"))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = _existing_columns(inspector)

    for column_name in _COLUMNS:
        if column_name not in existing:
            op.add_column("detections", sa.Column(column_name, sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "idx_detections_species_id"):
        op.create_index("idx_detections_species_id", "detections", ["species_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "idx_detections_species_id"):
        op.drop_index("idx_detections_species_id", table_name="detections")

    existing = _existing_columns(inspector)
    with op.batch_alter_table("detections") as batch:
        for column_name in _COLUMNS:
            if column_name in existing:
                batch.drop_column(column_name)
