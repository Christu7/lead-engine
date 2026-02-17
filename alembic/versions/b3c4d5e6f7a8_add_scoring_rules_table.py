"""add_scoring_rules_table

Revision ID: b3c4d5e6f7a8
Revises: f8e9a1b2c3d4
Create Date: 2026-02-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "f8e9a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scoring_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(255), nullable=False),
        sa.Column("operator", sa.String(50), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scoring_rules_client_active", "scoring_rules", ["client_id", "is_active"])

    op.add_column("leads", sa.Column("score_details", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "score_details")
    op.drop_index("ix_scoring_rules_client_active", table_name="scoring_rules")
    op.drop_table("scoring_rules")
