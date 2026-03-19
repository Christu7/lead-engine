"""add_api_key_store

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-19

Adds the api_key_store table for encrypted third-party API credentials.
No client_id — these are system-level configuration values.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_key_store",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("key_name", sa.String(100), nullable=False),
        sa.Column("key_value", sa.String(2000), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("key_name", name="uq_api_key_store_key_name"),
    )
    op.create_index(
        "ix_api_key_store_key_name",
        "api_key_store",
        ["key_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_api_key_store_key_name", table_name="api_key_store")
    op.drop_table("api_key_store")
