"""add_rbac

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-03-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add role column to users
    op.add_column(
        "users",
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
    )

    # Create user_clients junction table
    op.create_table(
        "user_clients",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Migrate existing user->client_id data into the junction table
    op.execute("""
        INSERT INTO user_clients (user_id, client_id)
        SELECT id, client_id FROM users WHERE client_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    # Drop client_id from users
    op.drop_index("ix_users_client_id", table_name="users")
    op.drop_constraint("fk_users_client_id", "users", type_="foreignkey")
    op.drop_column("users", "client_id")


def downgrade() -> None:
    op.add_column("users", sa.Column("client_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_client_id", "users", "clients", ["client_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_users_client_id", "users", ["client_id"])

    # Restore one client_id per user from junction table (take the first)
    op.execute("""
        UPDATE users u
        SET client_id = (
            SELECT client_id FROM user_clients uc WHERE uc.user_id = u.id LIMIT 1
        )
    """)

    op.drop_table("user_clients")
    op.drop_column("users", "role")
