"""Password security hardening: expiry, history, password_changed_at.

Revision ID: o1p2q3r4s5t6
Revises: n1o2p3q4r5s6
Create Date: 2026-03-30

Changes:
- Add password_expiry_days column to company_preferences (default 30, 0 = never).
- Add password_changed_at column to users (nullable, backfilled to now).
- Create password_history table for reuse prevention.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "o1p2q3r4s5t6"
down_revision = "n1o2p3q4r5s6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- company_preferences: password expiry setting --
    op.add_column(
        "company_preferences",
        sa.Column("password_expiry_days", sa.Integer(), nullable=False, server_default="30"),
    )

    # -- users: track when password was last changed --
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
    )
    op.execute("UPDATE users SET password_changed_at = CURRENT_TIMESTAMP WHERE password_changed_at IS NULL")

    # -- password_history: reuse prevention --
    op.create_table(
        "password_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_history")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_history_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_password_history_user_id_created_at"),
        "password_history",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_password_history_user_id_created_at"), table_name="password_history")
    op.drop_table("password_history")
    op.drop_column("users", "password_changed_at")
    op.drop_column("company_preferences", "password_expiry_days")
