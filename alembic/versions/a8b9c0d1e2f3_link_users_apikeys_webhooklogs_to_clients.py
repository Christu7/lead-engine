"""link_users_apikeys_webhooklogs_to_clients

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
Create Date: 2026-03-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users.client_id
    op.add_column(
        "users",
        sa.Column("client_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_client_id",
        "users", "clients",
        ["client_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_client_id", "users", ["client_id"])

    # api_keys.client_id
    op.add_column(
        "api_keys",
        sa.Column("client_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_api_keys_client_id",
        "api_keys", "clients",
        ["client_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_api_keys_client_id", "api_keys", ["client_id"])

    # webhook_logs.client_id
    op.add_column(
        "webhook_logs",
        sa.Column("client_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_webhook_logs_client_id",
        "webhook_logs", "clients",
        ["client_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_webhook_logs_client_id", "webhook_logs", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_logs_client_id", table_name="webhook_logs")
    op.drop_constraint("fk_webhook_logs_client_id", "webhook_logs", type_="foreignkey")
    op.drop_column("webhook_logs", "client_id")

    op.drop_index("ix_api_keys_client_id", table_name="api_keys")
    op.drop_constraint("fk_api_keys_client_id", "api_keys", type_="foreignkey")
    op.drop_column("api_keys", "client_id")

    op.drop_index("ix_users_client_id", table_name="users")
    op.drop_constraint("fk_users_client_id", "users", type_="foreignkey")
    op.drop_column("users", "client_id")
