"""add_routing_log_columns

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-02-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "routing_logs",
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "routing_logs",
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("routing_logs", "error")
    op.drop_column("routing_logs", "success")
