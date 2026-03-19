"""add_company_model_and_link_leads

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. CREATE TABLE companies ---
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("location_city", sa.String(255), nullable=True),
        sa.Column("location_state", sa.String(255), nullable=True),
        sa.Column("location_country", sa.String(255), nullable=True),
        sa.Column("apollo_id", sa.String(255), nullable=True),
        sa.Column("funding_stage", sa.String(100), nullable=True),
        sa.Column("annual_revenue_range", sa.String(100), nullable=True),
        sa.Column("tech_stack", postgresql.JSONB(), nullable=True),
        sa.Column("keywords", postgresql.JSONB(), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("founded_year", sa.Integer(), nullable=True),
        sa.Column("enrichment_data", postgresql.JSONB(), nullable=True),
        sa.Column("enrichment_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abm_status", sa.String(50), nullable=False, server_default="target"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("apollo_id", "client_id", name="uq_companies_apollo_id_client"),
        sa.UniqueConstraint("domain", "client_id", name="uq_companies_domain_client"),
    )
    op.create_index("ix_companies_client_id", "companies", ["client_id"])
    op.create_index("ix_companies_domain", "companies", ["domain"])
    op.create_index("ix_companies_apollo_id", "companies", ["apollo_id"])
    op.create_index("ix_companies_enrichment_status", "companies", ["enrichment_status"])
    op.create_index("ix_companies_abm_status", "companies", ["abm_status"])

    # --- 2. ALTER TABLE leads: add company_id ---
    op.add_column(
        "leads",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_leads_company_id",
        "leads",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_leads_company_id", "leads", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_leads_company_id", table_name="leads")
    op.drop_constraint("fk_leads_company_id", "leads", type_="foreignkey")
    op.drop_column("leads", "company_id")

    op.drop_index("ix_companies_abm_status", table_name="companies")
    op.drop_index("ix_companies_enrichment_status", table_name="companies")
    op.drop_index("ix_companies_apollo_id", table_name="companies")
    op.drop_index("ix_companies_domain", table_name="companies")
    op.drop_index("ix_companies_client_id", table_name="companies")
    op.drop_table("companies")
