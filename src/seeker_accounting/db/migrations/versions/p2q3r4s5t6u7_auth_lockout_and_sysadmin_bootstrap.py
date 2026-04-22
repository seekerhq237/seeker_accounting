"""Persist auth lockouts and convert sysadmin to explicit bootstrap setup.

Revision ID: p2q3r4s5t6u7
Revises: o1p2q3r4s5t6
Create Date: 2026-04-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p2q3r4s5t6u7"
down_revision = "o1p2q3r4s5t6"
branch_labels = None
depends_on = None

_DEFAULT_PASSWORD_HASH = "$2b$12$2oFr0yufRgIqPxy5ZioTKesrTlG0/BgwgKs4rXUxgSjcSjZKgWrr."


def upgrade() -> None:
    op.create_table(
        "authentication_lockouts",
        sa.Column("scope_key", sa.String(length=200), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("scope_key", name=op.f("pk_authentication_lockouts")),
    )

    op.add_column(
        "system_admin_credentials",
        sa.Column("is_configured", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.execute(
        sa.text(
            "UPDATE system_admin_credentials "
            "SET is_configured = CASE WHEN password_hash = :default_hash THEN 0 ELSE 1 END"
        ).bindparams(default_hash=_DEFAULT_PASSWORD_HASH)
    )
    op.execute(
        sa.text(
            "UPDATE system_admin_credentials "
            "SET password_hash = '', must_change_password = 1 "
            "WHERE password_hash = :default_hash"
        ).bindparams(default_hash=_DEFAULT_PASSWORD_HASH)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE system_admin_credentials "
            "SET password_hash = :default_hash, must_change_password = 1 "
            "WHERE is_configured = 0"
        ).bindparams(default_hash=_DEFAULT_PASSWORD_HASH)
    )
    op.drop_column("system_admin_credentials", "is_configured")
    op.drop_table("authentication_lockouts")
