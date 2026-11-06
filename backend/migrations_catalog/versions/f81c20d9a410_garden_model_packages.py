"""Keep garden taxonomy and geofences in the species catalogue.

Revision ID: f81c20d9a410
Revises: c4e8d1a7b2f3
"""

from alembic import op
import sqlalchemy as sa

revision = "f81c20d9a410"
down_revision = "c4e8d1a7b2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "garden_model_packages" not in tables:
        op.create_table(
            "garden_model_packages",
            sa.Column("sha256", sa.String(64), primary_key=True),
            sa.Column("payload", sa.Text(), nullable=False),
        )
    if "garden_taxon_bindings" not in tables:
        op.create_table(
            "garden_taxon_bindings",
            sa.Column("package_sha256", sa.String(64), nullable=False),
            sa.Column("taxon_id", sa.String(64), nullable=False),
            sa.Column("species_id", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("package_sha256", "taxon_id"),
            sa.ForeignKeyConstraint(["package_sha256"], ["garden_model_packages.sha256"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["species_id"], ["species.species_id"]),
        )


def downgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    for table in ("garden_taxon_bindings", "garden_model_packages"):
        if table in tables:
            op.drop_table(table)
