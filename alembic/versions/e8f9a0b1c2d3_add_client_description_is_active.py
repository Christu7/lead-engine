"""add_client_description_is_active

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-03-30

Adds:
  - description (String 500, nullable) to clients
  - is_active (Boolean, default true) to clients — soft-delete flag
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("description", sa.String(500), nullable=True))
    op.add_column(
        "clients",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("clients", "is_active")
    op.drop_column("clients", "description")
