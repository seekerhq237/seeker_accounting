"""Merge inventory P7 hardening and deferrals migration heads.

Revision ID: a14b00000025
Revises: a14b00000024, d000000000001
Create Date: 2026-05-06
"""

from __future__ import annotations

revision = "a14b00000025"
down_revision = ("a14b00000024", "d000000000001")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge-only migration; both parent branches carry the schema changes."""


def downgrade() -> None:
    """Merge-only migration; downgrade paths remain on the parent revisions."""
