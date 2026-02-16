"""add_multi_tenancy

Revision ID: a1b2c3d4e5f6
Revises: 2d7452f91b51
Create Date: 2026-02-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "2d7452f91b51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create clients table
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
    )

    # 2. Insert default client
    op.execute(
        "INSERT INTO clients (name, settings) VALUES ('Default', '{}'::jsonb)"
    )

    # 3. Add nullable client_id columns
    for table in ("leads", "enrichment_logs", "routing_logs"):
        op.add_column(table, sa.Column("client_id", sa.Integer(), nullable=True))

    # 4. Backfill existing rows with default client id
    conn = op.get_bind()
    default_id = conn.execute(
        sa.text("SELECT id FROM clients WHERE name = 'Default' LIMIT 1")
    ).scalar_one()

    for table in ("leads", "enrichment_logs", "routing_logs"):
        op.execute(f"UPDATE {table} SET client_id = {default_id} WHERE client_id IS NULL")

    # 5. Make client_id NOT NULL
    for table in ("leads", "enrichment_logs", "routing_logs"):
        op.alter_column(table, "client_id", nullable=False)

    # 6. Add foreign key constraints and index
    op.create_foreign_key(
        "fk_leads_client_id", "leads", "clients", ["client_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_enrichment_logs_client_id",
        "enrichment_logs",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_routing_logs_client_id",
        "routing_logs",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_leads_client_id", "leads", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_leads_client_id", table_name="leads")
    op.drop_constraint("fk_routing_logs_client_id", "routing_logs", type_="foreignkey")
    op.drop_constraint("fk_enrichment_logs_client_id", "enrichment_logs", type_="foreignkey")
    op.drop_constraint("fk_leads_client_id", "leads", type_="foreignkey")

    for table in ("routing_logs", "enrichment_logs", "leads"):
        op.drop_column(table, "client_id")

    op.drop_table("clients")
