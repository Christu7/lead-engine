"""add_apollo_id_to_leads

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("apollo_id", sa.String(length=255), nullable=True),
    )
    op.create_index(op.f("ix_leads_apollo_id"), "leads", ["apollo_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_leads_apollo_id"), table_name="leads")
    op.drop_column("leads", "apollo_id")
