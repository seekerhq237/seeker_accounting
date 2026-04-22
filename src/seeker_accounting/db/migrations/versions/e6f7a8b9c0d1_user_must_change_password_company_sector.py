"""Add must_change_password to users and sector_of_operation to companies.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-03-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "companies",
        sa.Column("sector_of_operation", sa.String(150), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "sector_of_operation")
    op.drop_column("users", "must_change_password")
