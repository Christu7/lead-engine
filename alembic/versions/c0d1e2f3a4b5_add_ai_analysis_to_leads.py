"""add_ai_analysis_to_leads

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-03-18 00:01:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("ai_analysis", postgresql.JSONB(), nullable=True))
    op.add_column("leads", sa.Column("ai_analyzed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("ai_status", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "ai_status")
    op.drop_column("leads", "ai_analyzed_at")
    op.drop_column("leads", "ai_analysis")
