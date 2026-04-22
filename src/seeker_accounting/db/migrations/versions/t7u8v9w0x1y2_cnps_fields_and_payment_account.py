"""Add CNPS number to employees, CNPS employer number to companies, and default payment account to employees.

Revision ID: t7u8v9w0x1y2
Revises: s6t7u8v9w0x1
Create Date: 2026-04-02 14:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t7u8v9w0x1y2"
down_revision: Union[str, None] = "s6t7u8v9w0x1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # employees — CNPS individual registration number (separate from NIF/tax_identifier)
    with op.batch_alter_table("employees") as batch_op:
        batch_op.add_column(
            sa.Column(
                "cnps_number",
                sa.String(50),
                nullable=True,
            ),
        )
        # default payment financial account — plain integer column (FK enforced by ORM; SQLite
        # does not support ALTER TABLE - ADD CONSTRAINT via DDL)
        batch_op.add_column(
            sa.Column(
                "default_payment_account_id",
                sa.Integer(),
                nullable=True,
            ),
        )
        batch_op.create_index(
            "ix_employees_default_payment_account_id",
            ["default_payment_account_id"],
        )

    # companies — CNPS employer registration number (separate from NIU/tax_identifier)
    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(
            sa.Column(
                "cnps_employer_number",
                sa.String(50),
                nullable=True,
            ),
        )



def downgrade() -> None:
    with op.batch_alter_table("employees") as batch_op:
        batch_op.drop_index("ix_employees_default_payment_account_id")
        batch_op.drop_column("default_payment_account_id")
        batch_op.drop_column("cnps_number")
    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_column("cnps_employer_number")
