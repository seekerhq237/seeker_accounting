"""Slice T30: DGI VAT-return statutory line codes.

Two surface changes:

1. ``tax_codes`` gains two orthogonal flags that drive bucketing into
   the DGI VAT-return statutory lines (L17 … L47):

   * ``is_export`` — taxable sales fall into L21 (zero-rated exports)
     instead of the rate's standard L17.  Independent of
     ``exemption_kind`` because exporters are *not* exempt; they
     simply apply a zero rate.
   * ``is_imported_service`` — purchases of foreign services fall
     into L29 (reverse-charge ready in T33).

   Both flags default to ``False`` so existing tax codes — including
   the seeded VAT-19.25 / VAT-EXEMPT pair — remain unchanged.

2. ``tax_return_lines`` gains a nullable ``base_amount`` column.
   DGI form lines such as L17 / L26 carry both an HT base and a VAT
   amount; older returns drafted with the 6-box internal scheme
   leave ``base_amount`` ``NULL`` and continue to render through the
   form-layout's legacy bridge.

The migration is purely additive — no rewriting of existing rows.
A small idempotent UPDATE flips ``is_export`` on tax codes that were
already seeded with ``return_box_code = 'L21'`` so future drafts
benefit immediately.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a14b00000006"
down_revision: Union[str, None] = "a14b00000005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # tax_codes: two new orthogonal flags.
    with op.batch_alter_table("tax_codes") as batch:
        batch.add_column(
            sa.Column(
                "is_imported_service",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "is_export",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # tax_return_lines: split base / tax amounts.
    with op.batch_alter_table("tax_return_lines") as batch:
        batch.add_column(
            sa.Column("base_amount", sa.Numeric(18, 2), nullable=True)
        )

    # Backfill: any tax code already wired to L21 is an export code.
    op.execute(
        "UPDATE tax_codes "
        "SET is_export = 1 "
        "WHERE return_box_code = 'L21'"
    )
    # Likewise tax codes wired to L29 are imported-services codes.
    op.execute(
        "UPDATE tax_codes "
        "SET is_imported_service = 1 "
        "WHERE return_box_code = 'L29'"
    )


def downgrade() -> None:
    with op.batch_alter_table("tax_return_lines") as batch:
        batch.drop_column("base_amount")
    with op.batch_alter_table("tax_codes") as batch:
        batch.drop_column("is_export")
        batch.drop_column("is_imported_service")
