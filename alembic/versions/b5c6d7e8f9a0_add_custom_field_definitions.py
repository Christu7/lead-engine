"""add_custom_field_definitions

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_field_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("field_key", sa.String(100), nullable=False),
        sa.Column("field_label", sa.String(255), nullable=False),
        sa.Column("field_type", sa.String(50), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("show_in_table", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id", "entity_type", "field_key",
            name="uq_custom_field_client_entity_key",
        ),
    )
    op.create_index("ix_custom_field_client_id", "custom_field_definitions", ["client_id"])
    op.create_index("ix_custom_field_entity_type", "custom_field_definitions", ["entity_type"])

    # GIN indexes on enrichment_data JSONB for fast custom-field queries
    op.create_index(
        "ix_leads_enrichment_data_gin",
        "leads",
        ["enrichment_data"],
        postgresql_using="gin",
        postgresql_ops={"enrichment_data": "jsonb_path_ops"},
    )
    op.create_index(
        "ix_companies_enrichment_data_gin",
        "companies",
        ["enrichment_data"],
        postgresql_using="gin",
        postgresql_ops={"enrichment_data": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_companies_enrichment_data_gin", table_name="companies")
    op.drop_index("ix_leads_enrichment_data_gin", table_name="leads")
    op.drop_index("ix_custom_field_entity_type", table_name="custom_field_definitions")
    op.drop_index("ix_custom_field_client_id", table_name="custom_field_definitions")
    op.drop_table("custom_field_definitions")
