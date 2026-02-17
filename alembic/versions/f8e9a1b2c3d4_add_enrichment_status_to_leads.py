"""add_enrichment_status_to_leads

Revision ID: f8e9a1b2c3d4
Revises: a1b2c3d4e5f6
Create Date: 2026-02-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f8e9a1b2c3d4"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("enrichment_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_index("ix_leads_enrichment_status", "leads", ["enrichment_status"])


def downgrade() -> None:
    op.drop_index("ix_leads_enrichment_status", table_name="leads")
    op.drop_column("leads", "enrichment_status")
