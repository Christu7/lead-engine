"""add_enrichment_mapping_to_custom_fields

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_field_definitions",
        sa.Column("enrichment_source", sa.String(50), nullable=True),
    )
    op.add_column(
        "custom_field_definitions",
        sa.Column("enrichment_mapping", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("custom_field_definitions", "enrichment_mapping")
    op.drop_column("custom_field_definitions", "enrichment_source")
