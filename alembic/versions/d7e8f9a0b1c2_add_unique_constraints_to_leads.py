"""add_unique_constraints_to_leads

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-03-28

Adds:
  - UniqueConstraint on (email, client_id) to prevent duplicate leads per client
  - Partial unique index on (apollo_id, client_id) WHERE apollo_id IS NOT NULL
    to prevent duplicate apollo leads per client
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove any existing duplicates before creating constraints.
    # Keep the earliest lead (lowest id) for each (email, client_id) pair.
    op.execute("""
        DELETE FROM leads
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM leads
            GROUP BY email, client_id
        )
    """)

    op.create_unique_constraint("uq_lead_email_client", "leads", ["email", "client_id"])

    op.create_index(
        "ix_leads_apollo_id_client_unique",
        "leads",
        ["apollo_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("apollo_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_leads_apollo_id_client_unique", table_name="leads")
    op.drop_constraint("uq_lead_email_client", "leads", type_="unique")
