"""Keep the measured light level with each detection (#945).

Existing detections have no reading and stay NULL: a light level is only ever
a measurement taken at the detection, never derived afterwards. Downgrade
removes the column alone; every other detection field is untouched.

Revision ID: d4a7c1e92b36
Revises: c1d734b9e201
"""

from alembic import op
import sqlalchemy as sa

revision = "d4a7c1e92b36"
down_revision = "c1d734b9e201"
branch_labels = None
depends_on = None

COLUMN = "illuminance_lux"


def _has_column() -> bool:
    return COLUMN in {row[1] for row in op.get_bind().execute(sa.text("PRAGMA table_info(detections)"))}


def upgrade() -> None:
    if _has_column():
        return
    # The bound matches ILLUMINANCE_MAX_LUX in app/services/ha_weather.py. The
    # typeof guard matters because SQLite would otherwise store text in a REAL column.
    op.execute(
        f"ALTER TABLE detections ADD COLUMN {COLUMN} REAL "
        f"CHECK ({COLUMN} IS NULL OR (typeof({COLUMN}) IN ('real', 'integer') "
        f"AND {COLUMN} >= 0 AND {COLUMN} <= 200000))"
    )


def downgrade() -> None:
    # Rebuilding detections would disrupt its evidence triggers and foreign keys.
    if _has_column():
        op.execute(f"ALTER TABLE detections DROP COLUMN {COLUMN}")
