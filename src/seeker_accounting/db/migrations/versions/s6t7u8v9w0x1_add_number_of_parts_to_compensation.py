"""Add number_of_parts (quotient familial) to employee_compensation_profiles.

Revision ID: s6t7u8v9w0x1
Revises: r5s6t7u8v9w0
Create Date: 2026-04-02 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s6t7u8v9w0x1"
down_revision: Union[str, None] = "r5s6t7u8v9w0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employee_compensation_profiles",
        sa.Column(
            "number_of_parts",
            sa.Numeric(precision=3, scale=1),
            nullable=False,
            server_default="1.0",
            comment="Quotient familial — IRPP family parts (1.0 = single, 2.0 = married, etc.)",
        ),
    )


def downgrade() -> None:
    op.drop_column("employee_compensation_profiles", "number_of_parts")
