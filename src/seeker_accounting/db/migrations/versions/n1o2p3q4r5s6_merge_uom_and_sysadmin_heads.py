"""Merge heads: revision_i3_uom_categories + system_admin_credentials.

Revision ID: n1o2p3q4r5s6
Revises: l5m6n7o8p9q0, m1n2o3p4q5r6
Create Date: 2026-03-30

This is an empty merge migration to resolve the two independent heads
that branched from k4l5m6n7o8p9.
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "n1o2p3q4r5s6"
down_revision = ("l5m6n7o8p9q0", "m1n2o3p4q5r6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
