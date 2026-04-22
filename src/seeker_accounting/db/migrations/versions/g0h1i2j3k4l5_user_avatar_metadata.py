"""Add user avatar metadata fields.

Revision ID: g0h1i2j3k4l5
Revises: a7b8c9d0e1f2
Create Date: 2026-03-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "g0h1i2j3k4l5"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_storage_path", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("avatar_original_filename", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("avatar_content_type", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("avatar_sha256", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("avatar_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_updated_at")
    op.drop_column("users", "avatar_sha256")
    op.drop_column("users", "avatar_content_type")
    op.drop_column("users", "avatar_original_filename")
    op.drop_column("users", "avatar_storage_path")
