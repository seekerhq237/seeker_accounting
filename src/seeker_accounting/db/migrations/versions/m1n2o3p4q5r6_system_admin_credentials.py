"""Create system_admin_credentials table and seed default sysadmin account.

Revision ID: m1n2o3p4q5r6
Revises: l1m2n3o4p5q6
Create Date: 2026-03-30

Changes:
- Create system_admin_credentials table (single-row design).
  Completely isolated from the application User model.
- Seed initial row: username='sysadmin', password=bcrypt('sys_admin'),
  must_change_password=True  (forced on first use).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m1n2o3p4q5r6"
down_revision = "l1m2n3o4p5q6"
branch_labels = None
depends_on = None

# Pre-computed bcrypt hash of default password 'sys_admin' (work factor 12).
_DEFAULT_PASSWORD_HASH = "$2b$12$2oFr0yufRgIqPxy5ZioTKesrTlG0/BgwgKs4rXUxgSjcSjZKgWrr."


def upgrade() -> None:
    op.create_table(
        "system_admin_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_admin_credentials")),
        sa.UniqueConstraint("username", name=op.f("uq_system_admin_credentials_username")),
    )

    # Seed the single sysadmin row
    op.execute(
        sa.text(
            "INSERT INTO system_admin_credentials (id, username, password_hash, must_change_password) "
            "VALUES (1, 'sysadmin', :pw_hash, 1)"
        ).bindparams(pw_hash=_DEFAULT_PASSWORD_HASH)
    )


def downgrade() -> None:
    op.drop_table("system_admin_credentials")
