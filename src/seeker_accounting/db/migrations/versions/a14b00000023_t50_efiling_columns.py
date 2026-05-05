"""T50: add e-filing scaffold columns to tax_returns.

Revision ID: a14b00000023
Revises: a14b00000022
Create Date: 2025-01-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a14b00000023"
down_revision: str | None = "a14b00000022"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # SHA-256 hex digest of the serialised payload for non-repudiation.
    op.add_column(
        "tax_returns",
        sa.Column("submission_payload_hash", sa.String(64), nullable=True),
    )
    # Acknowledgement ID returned by the e-filing authority (DGI portal).
    op.add_column(
        "tax_returns",
        sa.Column(
            "submission_acknowledgement_id", sa.String(120), nullable=True
        ),
    )
    # Timestamp of the authority's acknowledgement.
    op.add_column(
        "tax_returns",
        sa.Column(
            "submission_authority_timestamp", sa.DateTime(), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("tax_returns", "submission_authority_timestamp")
    op.drop_column("tax_returns", "submission_acknowledgement_id")
    op.drop_column("tax_returns", "submission_payload_hash")
