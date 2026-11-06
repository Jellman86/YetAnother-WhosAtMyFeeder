"""Keep coarse model taxonomy separate from canonical species identity.

Revision ID: a9e72c4d103b
Revises: f81c20d9a410
"""

from alembic import op
import sqlalchemy as sa

revision = "a9e72c4d103b"
down_revision = "f81c20d9a410"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("model_output_taxa")}
    if "taxonomic_group" not in columns:
        op.add_column(
            "model_output_taxa",
            sa.Column(
                "taxonomic_group",
                sa.String(8),
                sa.CheckConstraint(
                    "taxonomic_group IN ('bird', 'nonbird', 'unknown')", name="ck_model_output_taxonomic_group"
                ),
                nullable=False,
                server_default="unknown",
            ),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("model_output_taxa")}
    if "taxonomic_group" in columns:
        op.drop_column("model_output_taxa", "taxonomic_group")
