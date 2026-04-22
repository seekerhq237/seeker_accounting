"""add user_sessions table

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-04-02 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q3r4s5t6u7v8"
down_revision: Union[str, None] = "p2q3r4s5t6u7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("login_at", sa.DateTime(), nullable=False),
        sa.Column("logout_at", sa.DateTime(), nullable=True),
        sa.Column("logout_reason", sa.String(50), nullable=True),
        sa.Column("abnormal_explanation_code", sa.String(50), nullable=True),
        sa.Column("abnormal_explanation_note", sa.Text(), nullable=True),
        sa.Column(
            "abnormal_reviewed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("abnormal_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("app_version", sa.String(30), nullable=True),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("os_info", sa.String(255), nullable=True),
    )
    op.create_index("ix_user_sessions_user_company", "user_sessions", ["user_id", "company_id"])
    op.create_index("ix_user_sessions_logout_at", "user_sessions", ["logout_at"])
    op.create_index(
        "ix_user_sessions_abnormal_unreviewed",
        "user_sessions",
        ["company_id", "logout_reason", "abnormal_reviewed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_abnormal_unreviewed", table_name="user_sessions")
    op.drop_index("ix_user_sessions_logout_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_company", table_name="user_sessions")
    op.drop_table("user_sessions")
