"""Add company logo metadata fields.

Revision ID: f0a1b2c3d4e5
Revises: e6f7a8b9c0d1
Create Date: 2026-03-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f0a1b2c3d4e5"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("logo_storage_path", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("logo_original_filename", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("logo_content_type", sa.String(length=100), nullable=True))
    op.add_column("companies", sa.Column("logo_sha256", sa.String(length=64), nullable=True))
    op.add_column("companies", sa.Column("logo_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "logo_updated_at")
    op.drop_column("companies", "logo_sha256")
    op.drop_column("companies", "logo_content_type")
    op.drop_column("companies", "logo_original_filename")
    op.drop_column("companies", "logo_storage_path")