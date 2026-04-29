"""Slice T14: tax_code CAC split + return box codes.

Cameroon VAT is published as a single combined rate of 19.25 % which
is in fact the sum of:

* a base VAT rate of ``17.50 %``
* the additional Communal Centimes (CAC), levied at ``10 %`` of the
  base VAT (i.e. ``17.50 % * 10 % = 1.75 %``).

The combined ``19.25 %`` cannot be split back into its components
once it has been stored as a single number.  DGI returns and the
posted-tax-line aggregation pipeline both require the split, so this
migration adds first-class columns for it on ``tax_codes``:

* ``has_cac`` — boolean flag, defaults to ``False`` so existing tax
  codes (from other jurisdictions or already configured by the user)
  retain their current behaviour.
* ``base_rate_percent`` — the base portion of a split rate.
* ``cac_rate_percent`` — the CAC portion (expressed as a percentage of
  the base, *not* of the gross), so a Cameroon standard-rate code
  carries ``base_rate_percent = 17.5000`` and ``cac_rate_percent =
  10.0000``.
* ``exemption_kind`` — qualifier for non-taxable VAT codes.  Lets the
  return generator distinguish exports / exempt / state-borne / out
  of scope.  ``NULL`` for normal taxable codes.
* ``return_box_code`` — the DGI return line code (``L17``, ``L21`` …)
  that posted-tax-line aggregation will key on.  ``NULL`` keeps the
  tax code outside automatic return drafting.

This migration is purely additive — no data is rewritten.  Subsequent
slices (T15 settlement JE, T19 box mappings) consume the new columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a14b00000001"
down_revision: Union[str, None] = "f4567890123e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tax_codes") as batch:
        batch.add_column(
            sa.Column(
                "has_cac",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column("base_rate_percent", sa.Numeric(7, 4), nullable=True)
        )
        batch.add_column(
            sa.Column("cac_rate_percent", sa.Numeric(7, 4), nullable=True)
        )
        batch.add_column(
            sa.Column("exemption_kind", sa.String(length=30), nullable=True)
        )
        batch.add_column(
            sa.Column("return_box_code", sa.String(length=20), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("tax_codes") as batch:
        batch.drop_column("return_box_code")
        batch.drop_column("exemption_kind")
        batch.drop_column("cac_rate_percent")
        batch.drop_column("base_rate_percent")
        batch.drop_column("has_cac")
