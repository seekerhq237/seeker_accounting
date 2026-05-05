"""T49: add is_immutable to tax_return_lines; add TAX_RETURN_VIEWED audit event.

Revision ID: a14b00000022
Revises: a14b00000021
Create Date: 2025-01-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a14b00000022"
down_revision: str | None = "a14b00000021"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Add is_immutable column to tax_return_lines.
    # Default 0 (false) — existing rows are not immutable until a new
    # filing sets them.
    op.add_column(
        "tax_return_lines",
        sa.Column(
            "is_immutable",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("tax_return_lines", "is_immutable")
