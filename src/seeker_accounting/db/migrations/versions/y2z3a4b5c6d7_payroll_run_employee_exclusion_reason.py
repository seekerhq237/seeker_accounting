"""Add exclusion_reason to payroll_run_employees for operator-driven include/exclude.

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-04-22 16:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y2z3a4b5c6d7"
down_revision: Union[str, None] = "x1y2z3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_run_employees") as batch_op:
        batch_op.add_column(
            sa.Column(
                "exclusion_reason",
                sa.String(255),
                nullable=True,
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("payroll_run_employees") as batch_op:
        batch_op.drop_column("exclusion_reason")
