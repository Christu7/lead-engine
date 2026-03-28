"""add_superadmin_role

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-03-27

Promote all existing 'admin' users to 'superadmin'.

Prior to this migration, 'admin' was a platform-level role that could see all
clients and perform all operations.  The role system is now three-tier:

  superadmin  — platform owner, sees all clients, can create/delete clients
  admin       — per-client admin, sees only assigned clients
  member      — read/write leads and companies for assigned clients

All pre-existing 'admin' users mapped to what is now 'superadmin', so we
promote them.  There is no schema change — role is stored as String(50).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'superadmin' WHERE role = 'admin'")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'superadmin'")
